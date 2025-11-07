Advanced Patterns
=================

Advanced multi-agent configurations and collaboration patterns using real MassGen CLI and YAML.

.. note::

   All examples use real CLI commands and YAML configurations from the MassGen codebase.

Specialized Agent Teams
-----------------------

Creative Team
~~~~~~~~~~~~~

A specialized team for creative writing and storytelling tasks:

**Configuration:** ``@examples/teams/creative/creative_team.yaml``

.. code-block:: yaml

   agents:
     - id: "storyteller"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         reasoning:
           effort: "high"
         enable_web_search: true
       system_message: |
         Creative storyteller who excels at crafting engaging narratives
         with rich characters, vivid descriptions, and compelling plots.

     - id: "editor"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         reasoning:
           effort: "medium"
       system_message: |
         Skilled editor who evaluates creative works for structure,
         flow, and impact.

     - id: "critic"
       backend:
         type: "grok"
         model: "grok-3-mini"
       system_message: |
         Literary critic who analyzes creative works with a discerning eye.

**Run:**

.. code-block:: bash

   massgen \
     --config @examples/teams/creative/creative_team.yaml \
     "Write a short story about a robot who discovers music"

Research Team
~~~~~~~~~~~~~

Specialized configuration for research and analysis tasks:

**Configuration:** ``@examples/teams/research/research_team.yaml``

.. code-block:: yaml

   agents:
     - id: "information_gatherer"
       backend:
         type: "grok"
         model: "grok-3-mini"
         enable_web_search: true
       system_message: |
         Information gathering specialist with access to web search.
         Find authoritative sources and gather diverse perspectives.

     - id: "domain_expert"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         reasoning:
           effort: "medium"
         enable_web_search: true
         enable_code_interpreter: true
       system_message: |
         Domain expert with analytical capabilities.
         Provide deep subject matter expertise and analytical insights.

     - id: "synthesizer"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         reasoning:
           effort: "medium"
       system_message: |
         Synthesis specialist who combines multiple perspectives
         into coherent, actionable insights.

**Run:**

.. code-block:: bash

   massgen \
     --config @examples/teams/research/research_team.yaml \
     "Research quantum computing developments and synthesize key findings"

MCP Planning Mode
-----------------

Planning mode prevents MCP tools from executing during coordination, making collaboration safer for operations with side effects.

Filesystem Planning Mode
~~~~~~~~~~~~~~~~~~~~~~~~

**Configuration:** ``@examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml``

Five agents collaborating on filesystem tasks with planning mode:

.. code-block:: yaml

   agents:
     - id: "gemini_filesystem_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         cwd: "workspace"  # File operations handled via cwd

     # ... (4 more agents with filesystem access)

   orchestrator:
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         PLANNING MODE ACTIVE: During coordination, describe intended
         file operations without executing them. Only the winning agent
         will execute the planned operations.

**Run:**

.. code-block:: bash

   massgen \
     --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
     "Create a Python project structure with directories for src, tests, docs"

**How it works:**

1. **Coordination Phase**: All agents plan file operations without execution
2. **Voting**: Agents vote on the best approach
3. **Execution Phase**: Only the winning agent executes the planned operations

**Benefits:**

* Prevents multiple agents from modifying files simultaneously
* Safer for irreversible operations (file writes, deletions)
* Agents can plan complex operations collaboratively

Multi-Backend Orchestration
----------------------------

Leveraging Different Backend Strengths
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine backends for optimal performance:

.. code-block:: yaml

   agents:
     # Fast research with web search
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

     # Advanced reasoning
     - id: "analyst"
       backend:
         type: "openai"
         model: "gpt-5"
         reasoning:
           effort: "high"

     # Development with file operations
     - id: "developer"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"

     # Testing with code execution
     - id: "tester"
       backend:
         type: "ag2"
         agent_type: "ConversableAgent"
         llm_config:
           config_list:
             - model: "gpt-4"
               api_key: "${OPENAI_API_KEY}"
         code_execution_config:
           executor: "docker"
           work_dir: "testing"

**Use case:** Full development lifecycle with each agent specializing in their strength.

Context Paths for Project Integration
--------------------------------------

Multi-Agent Project Collaboration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Agents working on real codebases with granular permissions:

.. code-block:: yaml

   agents:
     - id: "code_analyzer"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         cwd: "analysis_workspace"

     - id: "implementer"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "implementation_workspace"

   orchestrator:
     context_paths:
       # Read access to source code
       - path: "/absolute/path/to/project/src"
         permission: "read"

       # Write access to tests
       - path: "/absolute/path/to/project/tests"
         permission: "write"

       # Write access for documentation
       - path: "/absolute/path/to/project/docs"
         permission: "write"

**Run:**

.. code-block:: bash

   massgen \
     --config your-project-config.yaml \
     "Analyze the codebase and add comprehensive tests"

**Safety features:**

* **During coordination**: All agents have read-only access
* **Final agent**: Gets configured permission (read or write)
* **Read-before-delete**: Agents must read files before deleting them

See :doc:`../user_guide/project_integration` for complete documentation.

Multi-Turn Workflows
--------------------

Interactive Development Session
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Build projects incrementally with maintained context:

.. code-block:: bash

   # Start interactive session with file operations
   massgen \
     --config @examples/tools/filesystem/claude_code_single.yaml

**Example session:**

.. code-block:: text

   You: Create a Flask API for user management
   [Agents create basic API structure]

   You: Add authentication with JWT tokens
   [Agents add auth using context of existing structure]

   You: Add database models for user profiles
   [Agents integrate database with existing auth]

   You: Write integration tests
   [Agents create tests covering all features]

   You: /quit

Each turn builds on previous work, maintaining full project context.

Advanced MCP Integration
-------------------------

Multi-Server MCP Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine multiple external tools:

.. code-block:: yaml

   agents:
     - id: "multi_tool_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         mcp_servers:
           # Web search
           - name: "search"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-brave-search"]
             env:
               BRAVE_API_KEY: "${BRAVE_API_KEY}"

           # Weather information
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@fak111/weather-mcp"]

           # Custom HTTP API
           - name: "custom_api"
             type: "streamable-http"
             url: "http://localhost:8080/mcp/sse"

         # Tool filtering
         allowed_tools:
           - "mcp__search__brave_web_search"
           - "mcp__weather__get_forecast"
           - "mcp__custom_api__query_data"

**Run:**

.. code-block:: bash

   massgen \
     --config @examples/tools/mcp/multimcp_gemini.yaml \
     "Find hotels in Paris, check the weather, and save recommendations"

AG2 Framework Integration
--------------------------

Hybrid MassGen + AG2 Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine MassGen orchestration with AG2 code execution:

.. code-block:: yaml

   agents:
     # Native MassGen agent with web search
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

     # AG2 agent with Docker code execution
     - id: "ag2_coder"
       backend:
         type: "ag2"
         agent_type: "ConversableAgent"
         llm_config:
           config_list:
             - model: "gpt-4"
               api_key: "${OPENAI_API_KEY}"
         code_execution_config:
           executor: "docker"
           work_dir: "coding"
           timeout: 120

**Run:**

.. code-block:: bash

   massgen \
     --config @examples/ag2/ag2_coder_case_study.yaml \
     "Build a data analysis pipeline with visualizations"

See :doc:`../user_guide/general_interoperability` for complete AG2 documentation.

Performance Optimization Patterns
----------------------------------

Cost-Effective Multi-Agent Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Optimize costs while maintaining quality:

.. code-block:: yaml

   agents:
     # Fast, cost-effective research
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"  # Very cost-effective
         enable_web_search: true

     # Affordable reasoning
     - id: "analyst"
       backend:
         type: "openai"
         model: "gpt-5-nano"  # Low-cost GPT-5 tier
         reasoning:
           effort: "medium"

     # Budget-friendly alternative perspectives
     - id: "critic"
       backend:
         type: "grok"
         model: "grok-3-mini"  # Affordable Grok tier

   orchestrator:
     max_rounds: 3  # Limit coordination rounds
     voting_config:
       threshold: 0.6  # Lower threshold for faster consensus

**Strategies:**

* Use flash/mini/nano models for most agents
* Reserve premium models for critical tasks
* Limit coordination rounds
* Set appropriate max_tokens
* Use local models (LM Studio) for development

Resource-Limited Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For development or resource-constrained environments:

.. code-block:: yaml

   agents:
     - id: "local_agent"
       backend:
         type: "lmstudio"
         model: "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF"
         port: 1234
         max_tokens: 2048

   orchestrator:
     max_rounds: 2
     timeout: 120

**Benefits:**

* Zero API costs
* Full privacy (local inference)
* No rate limits
* Great for testing configurations

Configuration Best Practices
-----------------------------

1. **Start Simple**

   * Test single agent configurations first
   * Add complexity incrementally
   * Verify each feature works before combining

2. **Match Backends to Tasks**

   * Gemini Flash: Fast research, cost-effective
   * GPT-5: Advanced reasoning, complex analysis
   * Claude Code: Development, file operations
   * Grok: Real-time information, alternative perspectives

3. **Use Planning Mode for Safety**

   * Enable for file operations
   * Use for external API calls
   * Prevent irreversible actions during coordination

4. **Organize Configurations**

   * Group by use case (research, creative, development)
   * Use descriptive agent IDs
   * Add comments explaining agent roles
   * Store in version control

5. **Test Incrementally**

   * Use ``--debug`` for troubleshooting
   * Test with simple questions first
   * Verify tool access works
   * Check logs for errors

Configuration Examples Repository
----------------------------------

All example configurations are in ``@examples/``:

**By Feature:**

* ``basic/`` - Single and multi-agent setups
* ``tools/`` - MCP, filesystem, web search, code execution
* ``teams/`` - Specialized agent teams
* ``ag2/`` - AG2 framework integration
* ``providers/`` - Provider-specific examples

**By Use Case:**

* Research and analysis
* Creative writing
* Software development
* Data analysis
* Project management

See the `Configuration Guide <https://github.com/Leezekun/MassGen/blob/main/@examples/README.md>`_ for the complete catalog.

Next Steps
----------

* :doc:`case_studies` - Real-world case studies with session logs
* :doc:`basic_examples` - Fundamental usage examples
* :doc:`../user_guide/mcp_integration` - MCP integration guide
* :doc:`../user_guide/file_operations` - File operations guide
* :doc:`../user_guide/multi_turn_mode` - Interactive mode guide
* :doc:`../reference/yaml_schema` - Complete YAML reference

Troubleshooting
---------------

**Configuration not loading:**

.. code-block:: bash

   # Verify YAML syntax
   python -c "import yaml; yaml.safe_load(open('your-config.yaml'))"

**Agents not collaborating:**

Check orchestrator configuration:

.. code-block:: yaml

   orchestrator:
     max_rounds: 5  # Allow enough rounds for convergence
     voting_config:
       threshold: 0.6  # Not too high (prevents consensus)

**MCP tools not working:**

Verify MCP server installation:

.. code-block:: bash

   # Test MCP server (example with weather)
   npx -y @modelcontextprotocol/server-weather

**Planning mode not activating:**

Ensure coordination config is present:

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true  # Must be under 'coordination'
