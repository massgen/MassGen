AG2 Framework Integration
==========================

**NEW in v0.0.28**

MassGen supports AG2 framework integration, enabling AG2 agents with code execution capabilities to collaborate alongside native MassGen agents.

What is AG2?
------------

AG2 is an agent framework that provides:

* Conversational and task-oriented agents
* Code execution capabilities (Python, Jupyter, Docker)
* Tool and function calling
* Multi-agent conversations

MassGen's adapter architecture allows AG2 agents to participate in MassGen's multi-agent coordination system with voting and consensus building.

Quick Start
-----------

**Single AG2 agent:**

.. code-block:: bash

   massgen \
     --config @examples/ag2/ag2_coder.yaml \
     "Write a Python script to analyze CSV data and create visualizations"

**AG2 + Native MassGen hybrid:**

.. code-block:: bash

   massgen \
     --config @examples/ag2/ag2_coder_case_study.yaml \
     "Compare AG2 and MassGen frameworks, use code to fetch documentation"

Installation
------------

AG2 integration requires additional dependencies:

.. code-block:: bash

   # Install AG2 support
   uv pip install -e ".[external]"

This installs the AG2 framework and adapter dependencies.

Configuration
-------------

Basic AG2 Agent
~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "ag2_coder"
       backend:
         type: ag2                  # External framework backend
         agent_config:
           type: assistant          # AG2 agent type
           name: "AG2_Coder"
           system_message: |
             You are a helpful coding assistant.
             Write Python code in markdown blocks for automatic execution.
           llm_config:
             api_type: "openai"     # LLM provider for AG2 agent
             model: "gpt-4o"
           code_execution_config:
             executor:
               type: "LocalCommandLineCodeExecutor"
               timeout: 60
               work_dir: "./code_execution_workspace"

AG2 Agent Types
~~~~~~~~~~~~~~~

**AssistantAgent** - Coding and task-oriented:

.. code-block:: yaml

   agent_config:
     type: assistant
     name: "Coder"
     system_message: "You write Python code"
     llm_config:
       api_type: "openai"
       model: "gpt-4o"
     code_execution_config:
       executor:
         type: "LocalCommandLineCodeExecutor"

**ConversableAgent** - General-purpose conversational:

.. code-block:: yaml

   agent_config:
     type: conversable
     name: "Assistant"
     system_message: "You are a helpful assistant"
     llm_config:
       api_type: "openai"
       model: "gpt-4o"

Code Execution Options
~~~~~~~~~~~~~~~~~~~~~~

**Local execution:**

.. code-block:: yaml

   code_execution_config:
     executor:
       type: "LocalCommandLineCodeExecutor"
       timeout: 60
       work_dir: "./workspace"

**Docker execution (isolated):**

.. code-block:: yaml

   code_execution_config:
     executor:
       type: "DockerCommandLineCodeExecutor"
       timeout: 120
       image: "python:3.11"
       work_dir: "/workspace"

**Jupyter notebook:**

.. code-block:: yaml

   code_execution_config:
     executor:
       type: "JupyterCodeExecutor"
       timeout: 60

**Cloud execution:**

.. code-block:: yaml

   code_execution_config:
     executor:
       type: "YepCodeCodeExecutor"
       api_key: "${YEPCODE_API_KEY}"

Hybrid Multi-Agent Setup
-------------------------

Combine AG2 and native MassGen agents:

.. code-block:: yaml

   agents:
     # AG2 agent with code execution
     - id: "ag2_coder"
       backend:
         type: ag2
         agent_config:
           type: assistant
           name: "AG2_Coder"
           system_message: "You write and execute Python code"
           llm_config:
             api_type: "openai"
             model: "gpt-4o"
           code_execution_config:
             executor:
               type: "LocalCommandLineCodeExecutor"
               timeout: 60
               work_dir: "./code_workspace"

     # Native Gemini agent with web search
     - id: "gemini_researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"

     # Native Claude agent with MCP tools
     - id: "claude_analyst"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         cwd: "claude_workspace"  # File operations handled via cwd
         mcp_servers:
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-weather"]

This setup enables:

* **AG2 agent** executes Python code for analysis
* **Gemini agent** researches information with web search
* **Claude agent** provides weather data and additional analysis
* All three collaborate through MassGen's coordination system

How It Works
------------

Adapter Architecture
~~~~~~~~~~~~~~~~~~~~

MassGen uses an adapter pattern to integrate external frameworks:

1. **ExternalAgentBackend** detects ``type: ag2``
2. **AG2Adapter** translates between MassGen and AG2 interfaces
3. AG2 agent participates in MassGen coordination
4. Async execution via AG2's ``a_generate_reply``

Coordination Flow
~~~~~~~~~~~~~~~~~

1. **Initial Answer Generation**

   * AG2 agent generates response using LLM
   * Can execute code if needed
   * Returns answer to MassGen orchestrator

2. **Coordination Phase**

   * AG2 agent sees other agents' responses
   * Participates in voting and consensus
   * Can refine based on others' insights

3. **Final Presentation**

   * If AG2 agent wins, it generates final answer
   * Can execute additional code if needed
   * Delivers coordinated result

Code Execution in Practice
---------------------------

AG2 agents can execute Python code during coordination:

**Example task:** "Analyze this dataset and create visualizations"

**AG2 agent workflow:**

1. Writes Python code to read and analyze data
2. Code automatically executes in configured environment
3. Results (including plots/charts) captured
4. Agent uses results to inform response
5. Collaborates with other agents on final answer

**Code example the agent might write:**

.. code-block:: python

   import pandas as pd
   import matplotlib.pyplot as plt

   # Read dataset
   df = pd.read_csv('data.csv')

   # Analyze
   summary = df.describe()

   # Visualize
   plt.figure(figsize=(10, 6))
   df['column'].hist(bins=30)
   plt.savefig('distribution.png')

The code executes, and the agent can reference the results in its answer.

Use Cases
---------

Data Analysis
~~~~~~~~~~~~~

AG2 agents excel at code-based data analysis:

.. code-block:: bash

   massgen \
     --config @examples/ag2/ag2_coder.yaml \
     "Analyze sales_data.csv and identify trends, create visualizations"

The AG2 agent:

* Reads and processes the CSV
* Performs statistical analysis
* Creates charts and graphs
* Collaborates with other agents on insights

Web Scraping
~~~~~~~~~~~~

AG2 agents can write and execute scraping code:

.. code-block:: bash

   massgen \
     --config @examples/ag2/ag2_coder.yaml \
     "Scrape the top 10 articles from Hacker News and save to JSON"

Framework Comparison
~~~~~~~~~~~~~~~~~~~~

Use AG2 alongside native agents for comparative analysis:

.. code-block:: bash

   massgen \
     --config @examples/ag2/ag2_coder_case_study.yaml \
     "Compare AG2 and MassGen frameworks, fetch and analyze documentation"

Testing and Validation
~~~~~~~~~~~~~~~~~~~~~~~

AG2 agents can write and execute test code:

.. code-block:: bash

   massgen \
     --config @examples/ag2/ag2_coder.yaml \
     "Write comprehensive unit tests for the authentication module and run them"

Benefits of AG2 Integration
----------------------------

**Code Execution**
   Native Python code execution within multi-agent coordination

**Framework Strengths**
   Leverage AG2's specialized capabilities alongside MassGen's coordination

**Gradual Migration**
   Mix AG2 and native agents in same workflow

**Future Extensibility**
   Adapter pattern enables integration of other frameworks (LangChain, CrewAI, etc.)

Configuration Reference
-----------------------

Complete AG2 Agent Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "ag2_agent"
       backend:
         type: ag2                          # Framework type

         agent_config:
           # Agent type: "assistant" or "conversable"
           type: assistant

           # Agent name
           name: "AG2_Agent"

           # System message (agent instructions)
           system_message: |
             Your instructions here

           # LLM configuration
           llm_config:
             api_type: "openai"              # openai, azure, anthropic, etc.
             model: "gpt-4o"                 # Model name
             temperature: 0.7                # Optional
             max_tokens: 2000                # Optional

           # Code execution (AssistantAgent only)
           code_execution_config:
             executor:
               type: "LocalCommandLineCodeExecutor"
               timeout: 60                   # Seconds
               work_dir: "./workspace"       # Execution directory

Executor Types
~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Executor Type
     - Description
   * - ``LocalCommandLineCodeExecutor``
     - Execute Python locally on host machine
   * - ``DockerCommandLineCodeExecutor``
     - Execute in Docker container for isolation
   * - ``JupyterCodeExecutor``
     - Execute in Jupyter notebook environment
   * - ``YepCodeCodeExecutor``
     - Cloud-based code execution service

LLM Providers for AG2
~~~~~~~~~~~~~~~~~~~~~~

AG2 agents support multiple LLM providers:

* ``openai`` - OpenAI API (GPT models)
* ``azure`` - Azure OpenAI
* ``anthropic`` - Claude models
* ``google`` - Gemini models
* Custom providers via AG2 configuration

Best Practices
--------------

1. **Isolated Execution** - Use Docker executor for untrusted code
2. **Timeout Configuration** - Set appropriate timeouts for code execution
3. **Workspace Management** - Organize code execution directories
4. **Error Handling** - AG2 agents handle code execution errors gracefully
5. **Hybrid Teams** - Combine AG2 code execution with native agent capabilities

Troubleshooting
---------------

**AG2 not installed:**

.. code-block:: bash

   uv pip install -e ".[external]"

**Code execution fails:**

* Check ``work_dir`` exists and is writable
* Verify ``timeout`` is sufficient
* Review code for syntax errors
* Check Docker setup (if using Docker executor)

**AG2 agent not responding:**

* Verify LLM API keys are set
* Check ``llm_config`` is correct
* Review logs for AG2-specific errors

Next Steps
----------

* :doc:`mcp_integration` - Combine AG2 with MCP tools
* :doc:`file_operations` - AG2 agents with file operations
* :doc:`multi_turn_mode` - AG2 in interactive mode
* :doc:`../quickstart/running-massgen` - More examples
