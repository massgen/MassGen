Tools and Capabilities
======================

MassGen provides a comprehensive tools ecosystem that enables AI agents to perform complex tasks through three complementary systems. Tools extend agent capabilities beyond text generation to include code execution, file operations, web search, external API integration, and custom functionality.

.. note::

   This is an overview of MassGen's tools ecosystem. For detailed guides, see:

   * :doc:`mcp_integration` - External tools via Model Context Protocol
   * :doc:`custom_tools` - Custom Python functions as tools

What Are Tools?
---------------

Tools in MassGen are capabilities that agents can invoke during task execution. Unlike traditional function calls in your code, these tools are:

* **Discoverable**: Agents automatically learn about available tools through JSON schemas
* **Backend-Agnostic**: The same tool works across Claude, Gemini, OpenAI, and all other backends
* **Safely Isolated**: Tools execute in controlled environments with timeouts and resource limits
* **Multimodal**: Tools can return text, images, audio, or structured data

Tool Systems Overview
---------------------

MassGen provides four ways for agents to access tools:

1. **Backend Built-in Tools**: Web search, code execution, file operations provided by model APIs
2. **MCP Integration**: External tools through the Model Context Protocol
3. **Custom Tools**: Your own Python functions registered via the Tool System
4. **AG2 Framework Tools**: Tools from the AG2 framework (when using AG2 backend)

1. Backend Built-in Tools
-------------------------

Different model providers offer built-in capabilities that agents can enable via YAML configuration.

**Key Capabilities:**

* **Web Search**: Real-time information from the internet (Gemini, Grok, Claude, OpenAI)
* **Code Execution**: Run Python code and scripts (OpenAI, Claude, Gemini, AG2)
* **File Operations**: Read, write, and modify files (Claude Code natively, others via MCP)

**Quick Example:**

.. code-block:: yaml

   agents:
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true         # Built-in web search
         enable_code_execution: true     # Built-in code execution

**Availability:**

See :doc:`backends` for the complete backend capabilities matrix showing which backends support which built-in tools.

2. MCP (Model Context Protocol) Integration
--------------------------------------------

The Model Context Protocol (MCP) is an open standard that connects AI agents to external tools and data sources. Think of it as USB-C for AI - a universal interface for tools.

**What You Can Do:**

* Connect to external APIs (Weather, Discord, Twitter, Notion)
* Access databases and file systems
* Use browser automation (Playwright)
* Search the web (Brave Search)
* Integrate with custom services

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
             args: ["-y", "@modelcontextprotocol/server-weather"]

**Key Features:**

* Standardized protocol for external tool integration
* Works across all MassGen backends (except Azure OpenAI)
* Support for multiple MCP servers per agent
* Tool filtering and safety controls
* Planning mode to prevent premature execution

.. seealso::
   :doc:`mcp_integration` - Complete guide with MCP server configuration, common servers, tool filtering, planning mode, and security best practices

3. Custom Tools System
-----------------------

MassGen's Custom Tools System allows you to register your own Python functions as tools that agents can discover and use. This enables you to extend agent capabilities with domain-specific functionality.

**What You Can Do:**

* Turn your Python functions into agent tools via YAML config
* Automatic schema generation from function signatures and docstrings
* Works across all MassGen backends (Claude, Gemini, OpenAI, etc.)
* No need to modify MassGen internals

**Your Tool File** (``my_tools/analyzer.py``):

.. code-block:: python

   from massgen.tool import ExecutionResult, TextContent
   import json

   async def analyze_data(dataset: str, metrics: list) -> ExecutionResult:
       """Analyze dataset and compute metrics.

       Args:
           dataset: Path to dataset file
           metrics: List of metrics to compute (e.g., ["mean", "median", "count"])

       Returns:
           ExecutionResult with analysis results
       """
       # Load and analyze data
       with open(dataset, 'r') as f:
           data = json.load(f)

       results = {}
       if "count" in metrics:
           results["count"] = len(data)
       if "mean" in metrics and data:
           results["mean"] = sum(data) / len(data)
       if "median" in metrics and data:
           sorted_data = sorted(data)
           mid = len(sorted_data) // 2
           results["median"] = sorted_data[mid]

       output = f"Analysis Results:\n{json.dumps(results, indent=2)}"
       return ExecutionResult(
           output_blocks=[TextContent(data=output)]
       )

**Your Config** (``config.yaml``):

.. code-block:: yaml

   agents:
     - id: "analyst"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         custom_tools:
           - name: "analyze_data"
             path: "my_tools/analyzer.py"
             function: "analyze_data"
             category: "data_science"

**Run:**

.. code-block:: bash

   massgen --config config.yaml "Analyze sales_data.csv"

.. seealso::
   :doc:`custom_tools` - Complete guide with working examples, built-in tools, configuration patterns, and troubleshooting

4. AG2 Framework Tools
-----------------------

When using the AG2 backend, agents gain access to the AG2 framework's execution environments and tools.

**Supported Executors:**

* ``local`` - Execute code on local machine
* ``docker`` - Execute in Docker container
* ``jupyter`` - Execute in Jupyter kernel
* ``yepcode`` - Execute in YepCode environment

**Configuration:**

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
           executor: "docker"
           work_dir: "coding"

See :doc:`general_interoperability` for detailed AG2 tool configuration and usage.

Combining Tool Systems
----------------------

The real power comes from combining different tool systems to create agents with comprehensive capabilities.

All Three Systems Together
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "full_stack_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"

         # 1. Built-in backend tools
         enable_web_search: true
         enable_code_execution: true

         # 2. External MCP tools
         mcp_servers:
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-weather"]

         # 3. Custom tools
         custom_tools:
           - path: "tools/analyzer.py"
             func: "analyze_data"
           - func: "run_python_script"

**Result**: Agent can search the web, execute code, check weather, and use your custom analysis functions.

Specialized Multi-Agent Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Different agents with different tool combinations:

.. code-block:: yaml

   agents:
     # Research agent: Web search + MCP
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true
         mcp_servers:
           - name: "brave_search"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-brave-search"]

     # Development agent: File operations + Custom tools
     - id: "developer"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"
         custom_tools:
           - func: "run_python_script"
           - func: "run_shell_script"

     # Data agent: Code execution + Custom analytics
     - id: "data_analyst"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         enable_code_interpreter: true
         custom_tools:
           - path: "tools/stats.py"
             func: "calculate_statistics"
           - path: "tools/viz.py"
             func: "create_visualization"

Quick Start Examples
--------------------

Built-in Tools
~~~~~~~~~~~~~~

.. code-block:: bash

   # Web search
   massgen --model gemini-2.5-flash \
     "Research the latest AI developments and summarize key trends"

   # Code execution
   massgen --model gpt-5-nano \
     "Calculate the first 100 prime numbers and plot their distribution"

MCP Tools
~~~~~~~~~

.. code-block:: bash

   # Single MCP server (weather)
   massgen \
     --config @examples/tools/mcp/gpt5_nano_mcp_example.yaml \
     "What's the weather forecast for New York this week?"

   # Multiple MCP servers
   massgen \
     --config @examples/tools/mcp/multimcp_gemini.yaml \
     "Find hotels in London and check the weather forecast"

Custom Tools
~~~~~~~~~~~~

.. code-block:: bash

   # Custom Python tools
   massgen \
     --config massgen/configs/tools/custom_tools/claude_code_custom_tool_example.yaml \
     "Calculate the sum of 15 and 27"

   # Custom tools with MCP
   massgen \
     --config massgen/configs/tools/custom_tools/gemini_custom_tool_with_mcp_example.yaml \
     "Test both custom and MCP tools together"

Choosing the Right Tool System
------------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Tool System
     - Best For
     - When to Use
   * - **Built-in Tools**
     - Web search, basic code execution, file ops
     - Quick setup, standard capabilities
   * - **MCP Integration**
     - External APIs, third-party services
     - Weather, databases, Discord, Twitter, browser automation
   * - **Custom Tools**
     - Domain-specific functionality
     - Your own business logic, specialized algorithms, internal APIs
   * - **AG2 Framework**
     - Complex multi-agent workflows
     - Research tasks, code generation with execution

Best Practices
--------------

Tool Configuration
~~~~~~~~~~~~~~~~~~

1. **Enable only needed tools**: Reduce API costs and improve agent focus
2. **Use MCP for external integrations**: Standardized, reusable protocol
3. **Create custom tools for domain logic**: Your unique functionality
4. **Test tools independently**: Verify each tool works before multi-agent use
5. **Document tool requirements**: Note required API keys, dependencies, and permissions

Security
~~~~~~~~

.. warning::

   Tools can execute code, access files, and call external APIs. Always:

   * Review third-party MCP servers before use
   * Use tool filtering (``allowed_tools``/``exclude_tools``) to restrict capabilities
   * Enable planning mode for tools with side effects
   * Store API keys in ``.env`` files, never in configs
   * Test in isolated environments first
   * Set timeouts to prevent long-running operations

See :doc:`project_integration` for secure file access configuration.

Performance
~~~~~~~~~~~

1. **Lazy loading**: Don't register unnecessary tools
2. **Category management**: Disable tool categories when not needed
3. **Tool filtering**: Reduce available tools to improve agent decision-making
4. **Caching**: MCP servers support caching for repeated requests
5. **Timeouts**: Set reasonable timeouts for all tools

Common Issues
-------------

**Backend doesn't support tool:**

.. code-block:: yaml

   # ❌ Grok doesn't support code execution
   backend:
     type: "grok"
     enable_code_interpreter: true

   # ✅ Use OpenAI instead
   backend:
     type: "openai"
     enable_code_interpreter: true

See :doc:`backends` for complete backend capabilities matrix.

**MCP server not found:**

.. code-block:: bash

   # Test MCP server
   npx -y @modelcontextprotocol/server-weather

   # Install globally for faster startup
   npm install -g @modelcontextprotocol/server-weather

**Custom tool not registered:**

* Verify the file path is correct relative to where you run massgen
* Check the function name matches exactly
* Ensure the function is defined in the file
* See :doc:`custom_tools` for detailed troubleshooting

Detailed Guides
---------------

For in-depth information on each tool system:

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: 🔌 MCP Integration

      External tools via Model Context Protocol

      * MCP server configuration
      * Common servers (weather, search, Discord)
      * Tool filtering and safety
      * Planning mode
      * Multi-server setups

      :doc:`Read the MCP Integration guide → <mcp_integration>`

   .. grid-item-card:: 🛠️ Custom Tools

      Your own Python functions as tools

      * Write Python functions as tools
      * Register via YAML config
      * Built-in tools (code execution, file operations)
      * Works across all backends
      * 58 working examples

      :doc:`Read the Custom Tools guide → <custom_tools>`

Related Documentation
---------------------

* :doc:`backends` - Complete backend capabilities matrix
* :doc:`file_operations` - File system operations and safety
* :doc:`project_integration` - Secure project access with context paths
* :doc:`general_interoperability` - Framework interoperability (including AG2)
* :doc:`../examples/basic_examples` - See tools in action
* :doc:`../reference/yaml_schema` - Complete YAML configuration reference

External Resources
------------------

* `MCP Server Registry <https://github.com/modelcontextprotocol/servers>`_ - Official MCP servers catalog
* `MCP Documentation <https://modelcontextprotocol.io/>`_ - Protocol specification
* `Custom Tools System README <https://github.com/Leezekun/MassGen/blob/main/massgen/tool/README.md>`_ - Complete technical overview
* `Config Examples <https://github.com/Leezekun/MassGen/tree/main/massgen/configs/tools>`_ - 58+ tool configuration examples

.. toctree::
   :maxdepth: 1

   mcp_integration
   custom_tools
