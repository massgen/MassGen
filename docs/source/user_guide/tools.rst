Tools and Capabilities
======================

MassGen agents access tools through backend capabilities and MCP (Model Context Protocol) integration. Tools enable agents to search the web, execute code, manipulate files, and interact with external systems.

.. note::

   Tools in MassGen are not Python classes to import. They are either:

   1. **Backend built-in tools** - Configured via YAML flags
   2. **MCP servers** - External tools via Model Context Protocol
   3. **File operations** - Via Claude Code or MCP filesystem server

Overview
--------

MassGen provides three ways for agents to use tools:

1. **Backend Built-in Tools**: Web search, code execution, file operations provided by model APIs
2. **MCP Integration**: External tools through the Model Context Protocol
3. **AG2 Framework Tools**: Tools from the AG2 framework (when using AG2 backend)

Backend Built-in Tools
-----------------------

Different backends provide different built-in capabilities. These are enabled via YAML configuration flags.

Web Search
~~~~~~~~~~

Enable web search for real-time information:

.. code-block:: yaml

   agents:
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

**Supported Backends:**

* ``openai`` - GPT models with web search
* ``claude`` - Claude with web search
* ``claude_code`` - Claude Code with web search
* ``gemini`` - Gemini with Google search
* ``grok`` - Grok with real-time search

**Example:**

.. code-block:: bash

   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     "What are the latest developments in quantum computing?"

Code Execution
~~~~~~~~~~~~~~

Enable code execution for computational tasks:

.. code-block:: yaml

   agents:
     - id: "coder"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         enable_code_interpreter: true

**Supported Backends:**

* ``openai`` - Code interpreter (Python)
* ``claude`` - Code execution
* ``claude_code`` - Full development environment
* ``gemini`` - Code execution
* ``ag2`` - Multiple execution environments

**Example:**

.. code-block:: bash

   massgen \
     --model gpt-5-nano \
     --backend openai \
     "Calculate the first 100 prime numbers and plot their distribution"

File Operations
~~~~~~~~~~~~~~~

Enable file system access:

.. code-block:: yaml

   agents:
     - id: "file_agent"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"           # Working directory

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

**Supported Backends:**

* ``claude_code`` - Native file tools (Read, Write, Edit, Bash, Grep, Glob)
* ``claude`` - Via MCP filesystem server
* ``gemini`` - Via MCP filesystem server
* ``grok`` - Via MCP filesystem server
* ``openai`` - Via MCP filesystem server

See :doc:`file_operations` for comprehensive file operation documentation.

Backend Tool Capabilities
~~~~~~~~~~~~~~~~~~~~~~~~~

Different backends support different built-in tools. For the complete and authoritative backend tool support matrix, see :doc:`backends`.

**Quick Summary:**

* **Web Search**: OpenAI, Claude, Claude Code, Gemini, Grok
* **Code Execution**: OpenAI, Claude, Claude Code, Gemini, AG2
* **File Operations**: Claude Code (native), others via MCP
* **MCP Support**: All backends except Azure OpenAI and LM Studio

See :doc:`backends` for the complete backend capabilities table with all features and limitations.

MCP (Model Context Protocol) Integration
-----------------------------------------

MCP allows agents to access external tools and services including web search, weather, filesystem access, Discord, Twitter, and many more.

**Quick Example:**

.. code-block:: yaml

   agents:
     - id: "agent_with_mcp"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         mcp_servers:
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@fak111/weather-mcp"]

**Key Features:**

* Common MCP servers (weather, search, filesystem)
* Multi-server configurations
* Tool filtering (allowed_tools/exclude_tools)
* Planning mode for safety (v0.0.29)
* HTTP and stdio transports

.. seealso::
   :doc:`mcp_integration` - Complete MCP guide with configuration, common servers, tool filtering, planning mode, and security considerations

AG2 Framework Tools
-------------------

When using the AG2 backend, agents can access AG2 framework tools:

.. code-block:: yaml

   agents:
     - id: "ag2_coder"
       backend:
         type: "ag2"
         agent_type: "ConversableAgent"
         llm_config:
           config_list:
             - model: "gpt-4"
               api_key: "${OPENAI_API_KEY}"
         code_execution_config:
           executor: "local"           # or "docker", "jupyter"
           work_dir: "coding"

**Supported Executors:**

* ``local`` - Execute code on local machine
* ``docker`` - Execute in Docker container
* ``jupyter`` - Execute in Jupyter kernel
* ``yepcode`` - Execute in YepCode environment

See :doc:`ag2_integration` for detailed AG2 tool configuration.

Tool Configuration Patterns
----------------------------

Combining Built-in and MCP Tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use both backend tools and MCP servers:

.. code-block:: yaml

   agents:
     - id: "full_stack_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"

         # Built-in tools
         enable_web_search: true
         enable_code_execution: true

         # External MCP tools
         mcp_servers:
           - name: "database"
             type: "stdio"
             command: "npx"
             args: ["-y", "@custom/database-mcp"]

Specialized Agent Tools
~~~~~~~~~~~~~~~~~~~~~~~

Configure different tools for different agents:

.. code-block:: yaml

   agents:
     # Research agent with web search
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

     # Development agent with file operations
     - id: "developer"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"

     # Data agent with MCP database access
     - id: "data_analyst"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         enable_code_interpreter: true
         mcp_servers:
           - name: "database"
             type: "stdio"
             command: "npx"
             args: ["-y", "@custom/db-server"]

Tool Usage Examples
-------------------

Web Search Example
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Single agent with web search
   massgen \
     --model gemini-2.5-flash \
     "Research the latest AI developments and summarize key trends"

   # Multi-agent research
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     "Compare renewable energy adoption rates across different countries"

Code Execution Example
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Code generation and execution
   massgen \
     --model gpt-5-nano \
     "Write and execute a Python script to analyze CSV data and create visualizations"

   # Multi-agent coding
   massgen \
     --config @examples/ag2/ag2_coder.yaml \
     "Create a web scraper for product prices and generate a comparison report"

File Operations Example
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # File operations with Claude Code
   massgen \
     --config @examples/tools/filesystem/claude_code_single.yaml \
     "Create a Python project structure with tests and documentation"

   # Multi-agent file collaboration
   massgen \
     --config @examples/tools/filesystem/claude_code_context_sharing.yaml \
     "Analyze code quality and generate improvement recommendations"

MCP Tools Example
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Weather information
   massgen \
     --config @examples/tools/mcp/gpt5_nano_mcp_example.yaml \
     "What's the weather forecast for New York this week?"

   # Multi-server MCP
   massgen \
     --config @examples/tools/mcp/multimcp_gemini.yaml \
     "Find hotels in London and check the weather forecast"

Tool Configuration Best Practices
----------------------------------

1. **Enable only needed tools**: Reduce API costs and improve focus
2. **Use MCP for external integrations**: Standardized protocol for tools
3. **Combine backend strengths**: Use different backends for different tool needs
4. **Test tools independently**: Verify MCP servers work before multi-agent use
5. **Filter dangerous tools**: Use allowed_tools/exclude_tools for safety
6. **Use planning mode for safety**: Enable for MCP tools with side effects
7. **Document tool requirements**: Note required API keys and dependencies

Security Considerations
-----------------------

File Operations
~~~~~~~~~~~~~~~

.. warning::

   Agents with file operations can read, write, modify, and delete files within permitted directories.

   * Only grant access to safe directories
   * Use read-only permissions when possible
   * Test in isolated environments first
   * Back up important files before granting write access

See :doc:`project_integration` for secure file access configuration.

MCP Tool Safety
~~~~~~~~~~~~~~~

* **Review MCP servers**: Verify third-party MCP server code
* **Use tool filtering**: Restrict dangerous operations
* **Enable planning mode**: Prevent execution during coordination
* **Monitor tool usage**: Check logs for unexpected tool calls
* **Set timeouts**: Prevent long-running operations

API Key Management
~~~~~~~~~~~~~~~~~~

* **Never commit keys**: Use environment variables only
* **Use .env files**: Keep credentials in .env (gitignored)
* **Rotate keys regularly**: Update API keys periodically
* **Monitor usage**: Track API costs and rate limits

Troubleshooting
---------------

**Tool not working:**

Check that the backend supports the tool:

.. code-block:: yaml

   # Grok doesn't support code execution
   backend:
     type: "grok"
     model: "grok-3-mini"
     enable_code_interpreter: true  # ❌ Not supported

   # Use OpenAI instead
   backend:
     type: "openai"
     model: "gpt-5-nano"
     enable_code_interpreter: true  # ✅ Supported

**MCP server not found:**

Ensure the MCP server package is available:

.. code-block:: bash

   # Test MCP server installation
   npx -y @fak111/weather-mcp

   # Install globally for faster startup
   npm install -g @fak111/weather-mcp

**File operations failing:**

Check workspace configuration:

.. code-block:: yaml

   # Correct workspace setup
   agents:
     - backend:
         type: "claude_code"
         cwd: "workspace"            # ✅ Directory exists

   orchestrator:
     snapshot_storage: "snapshots"   # ✅ Configured
     agent_temporary_workspace: "temp"  # ✅ Configured

**MCP tool not executing:**

Verify tool filtering configuration:

.. code-block:: yaml

   # If using allowed_tools, ensure the tool is listed
   allowed_tools:
     - "mcp__weather__get_current_weather"  # Tool name must match exactly

   # Check tool name with --debug flag
   massgen --debug --config your-config.yaml "..."

Next Steps
----------

* :doc:`mcp_integration` - Complete MCP integration guide
* :doc:`file_operations` - File system operations
* :doc:`project_integration` - Secure project access
* :doc:`ag2_integration` - AG2 framework tools
* :doc:`../examples/basic_examples` - See tools in action
* :doc:`backends` - Backend tool capabilities

Additional Resources
--------------------

* `MCP Server Registry <https://github.com/modelcontextprotocol/servers>`_ - Official MCP servers
* `MCP Documentation <https://modelcontextprotocol.io/>`_ - Protocol specification
* `Backend Configuration Guide <https://github.com/Leezekun/MassGen/blob/main/@examples/BACKEND_CONFIGURATION.md>`_ - Detailed backend settings
* :doc:`../reference/yaml_schema` - Complete YAML reference
