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

**First-Time Setup:**

The wizard consists of two steps:

1. **API Key Setup** (if no cloud provider keys detected)

   * Prompts for OpenAI, Anthropic, Google, or other cloud provider API keys
   * Saves to ``~/.config/massgen/.env``
   * Skipped if keys already exist

2. **Configuration Setup**

   * Option to browse ready-to-use configs/examples
   * Option to build from templates (Simple Q&A, Research, Code & Files, etc.)
   * Asks "Save as default?" when browsing existing configs
   * Launches directly into interactive mode

**After Setup:**

* **No arguments** → Starts multi-turn conversation mode if default config chosen
* **With question** → Runs single query using default config

CLI Parameters
--------------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Parameter
     - Description
   * - ``--config PATH``
     - Path to YAML configuration file with agent definitions, model parameters, backend parameters and UI settings.
       With ``--quickstart``, this value is treated as the output filename under ``.massgen/`` (for example,
       ``--quickstart --config team-config`` saves ``.massgen/team-config.yaml``)
   * - ``--select``
     - Interactively select from available configurations (user configs, project configs, current directory, package examples). Uses hierarchical navigation: category → config
   * - ``--backend TYPE``
     - Backend type for quick setup without config file. Options: ``claude``, ``claude_code``, ``gemini``, ``grok``, ``openai``, ``azure_openai``, ``zai``
   * - ``--model NAME``
     - Model name for quick setup (e.g., ``gemini-2.5-flash``, ``gpt-5-nano``). Mutually exclusive with ``--config``
   * - ``--system-message TEXT``
     - System prompt for the agent in quick setup mode. Omitted if ``--config`` is provided
   * - ``--cwd-context {ro,rw,read,write}``
     - Add the current working directory to ``orchestrator.context_paths`` for this run. ``ro/read`` grants read-only access, ``rw/write`` grants write permission
   * - ``--plan``
     - Planning-only mode. Agents create a structured task plan without auto-executing it
   * - ``--plan-depth {dynamic,shallow,medium,deep}``
     - Controls plan granularity for ``--plan`` mode
   * - ``--plan-steps N``
     - Optional explicit task-count target for planning output (must be > 0)
   * - ``--plan-chunks N``
     - Optional explicit chunk-count target for planning output (must be > 0)
   * - ``--broadcast {human,agents,false}``
     - Planning collaboration mode: ask user questions, coordinate among agents, or run fully autonomous
   * - ``--plan-and-execute``
     - Full workflow: create a plan, then execute it immediately
   * - ``--execute-plan PLAN_PATH``
     - Execute an existing plan by plan directory, plan ID, or ``latest``
   * - ``--no-display``
     - Disable real-time streaming UI coordination display (fallback to simple text output)
   * - ``--no-logs``
     - Disable real-time logging
   * - ``--debug``
     - Enable debug mode with verbose logging. Debug logs saved to ``agent_outputs/log_{time}/massgen_debug.log``
   * - ``--session-id ID``
     - Load memory from a previous session by ID (e.g., ``session_20251028_143000``). Allows continuing conversations with memory context from prior runs. Use with ``--list-sessions`` to find available sessions
   * - ``--list-sessions``
     - List all available memory sessions with their metadata (session IDs, timestamps, models, status). Sessions are automatically tracked in ``~/.massgen/sessions.json``
   * - ``--web``
     - Start the WebUI server instead of the terminal UI. Opens a browser-based interface with real-time agent streaming, vote visualization, and workspace browsing
   * - ``--web-host HOST``
     - Host address for the WebUI server (default: ``127.0.0.1``). Use ``0.0.0.0`` to allow external connections
   * - ``--web-port PORT``
     - Port for the WebUI server (default: ``8000``)
   * - ``--no-browser``
     - Don't auto-open browser when using ``--web`` with a question. Useful for automation or when running on servers
   * - ``--output-file PATH``
     - Write final answer to specified file path. Works in any mode (automation, interactive, etc.). Useful for capturing agent responses in scripts or pipelines
   * - ``--inbox-dir PATH``
     - Expose a file inbox for programmatic mid-stream steering. A caller drops a message with ``massgen.steering.send_steering_message()`` and the orchestrator delivers it to the running agent(s) — the headless equivalent of typing into the TUI/WebUI. The resolved directory is announced as ``RUNTIME_INBOX:`` in automation output. See :doc:`../user_guide/integration/automation`
   * - ``--logfire``
     - Enable Logfire observability for structured tracing of LLM calls, tool executions, and orchestration. Requires Logfire token (via ``logfire auth login`` or ``LOGFIRE_TOKEN`` env var). See :doc:`../user_guide/logging` for setup details
   * - ``"<your question>"``
     - Optional single-question input. If omitted, MassGen enters interactive chat mode

Mode Settings
~~~~~~~~~~~~~

These flags mirror the TUI mode bar toggles, allowing CLI control of execution modes.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Parameter
     - Description
   * - ``--single-agent [AGENT_ID]``
     - Single-agent mode. Uses only one agent from the config. Optionally specify an agent ID; defaults to the first agent if omitted
   * - ``--coordination-mode {parallel,decomposition}``
     - Coordination mode: ``parallel`` (voting-based, default) or ``decomposition`` (subtask-based). Overrides ``coordination_mode`` from config
   * - ``--quick``
     - Quick mode: disable refinement. Agents produce one answer with no voting loop. Equivalent to TUI "Refine OFF" toggle
   * - ``--personas {off,perspective,implementation,methodology}``
     - Enable parallel persona generation with specified diversity mode. ``off`` disables persona generation. Requires parallel coordination mode

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

Interactive Config Selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Browse and select from available configurations
   massgen --select

   # After selection, optionally provide a question
   massgen --select "Your question here"

   # The selector shows configs from:
   # - User configs: ~/.config/massgen/agents/
   # - Project configs: .massgen/*.yaml
   # - Current directory: *.yaml
   # - Package examples: Built-in example configs

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

Quick CWD Context Access
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Add current directory as read-only context
   massgen --config my_config.yaml --cwd-context ro "Review this codebase"

   # Add current directory as writable context
   massgen --config my_config.yaml --cwd-context rw "Apply the requested refactor"

.. note::

   In the Textual TUI, ``--cwd-context`` initializes the same CWD context state as the ``Ctrl+P`` toggle.
   In Execute mode, ``Ctrl+P`` is intentionally blocked to avoid changing context scope mid-execution.

Mode Settings
~~~~~~~~~~~~~

.. code-block:: bash

   # Quick mode: one answer per agent, no refinement loop
   massgen --quick --config my_config.yaml "Summarize this paper"

   # Single agent from a multi-agent config
   massgen --single-agent --config my_config.yaml "Quick question"

   # Single agent by ID
   massgen --single-agent agent_b --config my_config.yaml "Quick question"

   # Fastest: single agent + quick mode
   massgen --single-agent --quick --config my_config.yaml "What is 2+2?"

   # Persona-diverse parallel execution
   massgen --personas perspective --config my_config.yaml "Design a logo"

   # Decomposition mode (subtask-based)
   massgen --coordination-mode decomposition --config my_config.yaml "Build a web app"

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

Session Management
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # List available memory sessions
   massgen --list-sessions

   # Load session from previous run
   massgen --session-id session_20251028_143000 \
     "What did we discuss about the backend architecture?"

   # Interactive mode with previous session
   massgen --session-id session_20251028_143000 \
     --config my_config.yaml

   # Session can also be specified in YAML config
   # Add to your config.yaml:
   #   session_id: "session_20251028_143000"

WebUI Mode
~~~~~~~~~~

.. code-block:: bash

   # Start WebUI on default localhost:8000
   massgen --web

   # Custom host and port (for external access)
   massgen --web --web-host 0.0.0.0 --web-port 3000

   # With a specific config
   massgen --web --config @examples/basic/multi/three_agents_default

   # Combine with debug mode
   massgen --web --debug --config my_config.yaml

OpenAI-Compatible HTTP Server (``massgen serve``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run MassGen as an OpenAI-compatible HTTP API (FastAPI + Uvicorn).

**Endpoints:**

* ``GET /health`` - Health check endpoint
* ``POST /v1/chat/completions`` - OpenAI-compatible chat completions (non-streaming only)

.. note::

   Streaming (``stream: true``) is not yet supported. The server will return HTTP 501
   if streaming is requested. Use ``stream: false`` for all requests.

.. code-block:: bash

   # Start server (defaults: host 0.0.0.0, port 4000)
   massgen serve

   # Custom bind
   massgen serve --host 127.0.0.1 --port 4000

   # Provide a default config
   massgen serve --config path/to/config.yaml

   # Enable auto-reload for development
   massgen serve --reload

   # Health check
   curl http://localhost:4000/health

   # OpenAI-compatible Chat Completions
   # Note: When running with --config, the "model" parameter is ignored
   # to ensure the server uses the agent team defined in your YAML.
   curl http://localhost:4000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"massgen","messages":[{"role":"user","content":"hi"}],"stream":false}'

**Response Format:**

The server returns responses with the final synthesized answer in ``content`` and all agent traces in ``reasoning_content``:

.. code-block:: json

   {
     "choices": [{
       "message": {
         "role": "assistant",
         "content": "The final answer from the agent team.",
         "reasoning_content": "[system] Starting coordination...\n[agent_1] Analyzing...\n[orchestrator] Vote: agent_1"
       },
       "finish_reason": "stop"
     }]
   }

**Environment variables (optional):**

* ``MASSGEN_SERVER_HOST`` (default: ``0.0.0.0``)
* ``MASSGEN_SERVER_PORT`` (default: ``4000``)
* ``MASSGEN_SERVER_DEFAULT_CONFIG`` (default: unset)
* ``MASSGEN_SERVER_DEBUG`` (default: ``false``)

Output to File
~~~~~~~~~~~~~~

.. code-block:: bash

   # Save agent response to a file
   massgen --output-file results.txt "Summarize the key points of machine learning"

   # With config and output file
   massgen --config my_config.yaml --output-file report.md "Generate a project report"

Logfire Observability
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Enable structured tracing with Logfire
   massgen --logfire --config your_config.yaml "Your question"

   # Combine with debug mode for maximum observability
   massgen --logfire --debug --config your_config.yaml "Your question"

   # Or enable via environment variable
   export MASSGEN_LOGFIRE_ENABLED=true
   massgen --config your_config.yaml "Your question"

See :doc:`../user_guide/logging` for detailed Logfire setup instructions.

Additional Commands
-------------------

Log Analysis (``massgen logs``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Analyze and browse session logs without manual file navigation.

.. code-block:: bash

   # Summary of most recent run
   massgen logs

   # Full tool breakdown
   massgen logs tools

   # List recent runs
   massgen logs list

   # Open log directory in file manager
   massgen logs open

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Subcommand
     - Description
   * - ``massgen logs`` or ``massgen logs summary``
     - Display run summary with tokens, rounds, and top tools
   * - ``massgen logs tools``
     - Full tool breakdown table sorted by execution time
   * - ``massgen logs tools --sort calls``
     - Sort tools by call count instead of time
   * - ``massgen logs list``
     - List recent runs with timestamps, costs, questions, and analysis status
   * - ``massgen logs list --analyzed``
     - Show only logs with ANALYSIS_REPORT.md
   * - ``massgen logs list --unanalyzed``
     - Show only logs without analysis
   * - ``massgen logs list --limit 20``
     - Show more runs (default: 10)
   * - ``massgen logs analyze``
     - Generate analysis prompt for use in coding CLIs
   * - ``massgen logs analyze --mode self``
     - Run multi-agent self-analysis using a preset MassGen team (customizable via ``--config``)
   * - ``massgen logs open``
     - Open log directory in system file manager

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--log-dir PATH``
     - Analyze a specific log directory instead of the most recent
   * - ``--json``
     - Output raw JSON for scripting
   * - ``--mode {prompt,self}``
     - For ``analyze``: ``prompt`` (default) outputs a prompt; ``self`` runs multi-agent analysis
   * - ``--ui {automation,rich_terminal,webui}``
     - For ``analyze --mode self``: UI mode (default: ``rich_terminal``)
   * - ``--config PATH``
     - For ``analyze --mode self``: Custom analysis config file

Share Session (``massgen export``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Share a session via GitHub Gist for easy collaboration.

.. code-block:: bash

   # Share the most recent session
   massgen export

   # Share a specific session
   massgen export log_20251218_134125_867383

**Prerequisites:** Requires GitHub CLI (``gh``) to be installed and authenticated.

.. code-block:: bash

   # Install gh (macOS)
   brew install gh

   # Authenticate
   gh auth login

**Output:**

.. code-block:: text

   Sharing session from: .massgen/massgen_logs/log_20251218_134125/turn_1/attempt_1
   Collecting files...
   Uploading 45 files (1,234,567 bytes)...

   Share URL: https://massgen.github.io/MassGen-Viewer/?gist=abc123def456

   Anyone with this link can view the session (no login required).

The URL opens the MassGen Viewer with the session's coordination timeline, answers, votes, and tool usage.

Session Viewer (``massgen viewer``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

View any MassGen session in the full Textual TUI (read-only). Useful for observing ``--automation`` runs, replaying completed sessions, and monitoring cloud/CI runs.

.. code-block:: bash

   # View the most recent session
   massgen viewer

   # View a specific log directory
   massgen viewer /path/to/log_dir

   # Interactive session picker
   massgen viewer --pick

   # Replay at real-time speed (default: instant)
   massgen viewer /path/to/log_dir --replay-speed 1

   # View in browser via textual-serve
   massgen viewer /path/to/log_dir --web --port 9000

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``log_dir``
     - Path to log directory (positional, optional). Default: most recent session
   * - ``--turn N``
     - View a specific turn (default: latest)
   * - ``--attempt N``
     - View a specific attempt (default: latest)
   * - ``--replay-speed FLOAT``
     - Playback speed for completed sessions. ``0`` = instant (default), ``1`` = real-time, ``2`` = 2x speed
   * - ``--pick``
     - Interactively pick from recent sessions
   * - ``--web``
     - Serve the viewer TUI in a browser via ``textual-serve``
   * - ``--port PORT``
     - Port for ``--web`` mode (default: 8000)

The viewer shows the exact same TUI as a normal interactive run — agent panels, tool calls, votes, and final presentation — but in read-only mode with the input area hidden.

Manage Shared Sessions (``massgen shares``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

List and manage your shared sessions.

.. code-block:: bash

   # List your shared sessions
   massgen shares list

   # Delete a shared session
   massgen shares delete <gist_id>

See Also
--------

* :doc:`../quickstart/running-massgen` - Detailed usage examples
* :doc:`yaml_schema` - YAML configuration reference
* :doc:`supported_models` - Available models and backends
* :doc:`../user_guide/logging` - Complete logging and debugging guide
