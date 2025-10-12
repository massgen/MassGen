Backend Selection Guide
=======================

This guide helps you choose the best backend for your specific use case. While :doc:`supported_models` provides technical specifications, this guide focuses on practical decision-making.

Quick Decision Tree
-------------------

**Do you need file operations?**

* **YES** → Claude Code (best) or MCP filesystem (any backend)
* **NO** → Continue...

**Do you need maximum power/speed?**

* **Power + Reasoning** → GPT-5 (OpenAI) or Claude Sonnet 4
* **Speed + Cost** → Gemini 2.5 Flash or GPT-5-nano

**Do you need web search?**

* **Real-time + comprehensive** → Grok (Live Search)
* **Research** → Gemini (Google Search) or OpenAI (Responses API)

**Do you need code execution?**

* **Development tools** → Claude Code
* **Data analysis** → OpenAI (Code Interpreter) or Gemini

**Budget constrained?**

* **Ultra-low cost** → LM Studio (local, free)
* **Balanced** → Gemini Flash, GPT-5-nano

**Enterprise/Corporate?**

* **Azure deployments** → Azure OpenAI
* **Compliance needs** → Check provider's data policies

Backend Comparison by Use Case
-------------------------------

Research & Analysis Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~

**Best Options**:

1. **Gemini 2.5 Flash** - Fast, cheap, Google Search integration
2. **Grok-3-mini** - Real-time Live Search, current events
3. **GPT-5-nano** - Balanced reasoning with web search

.. list-table::
   :header-rows: 1
   :widths: 20 15 15 15 35

   * - Backend
     - Speed
     - Cost
     - Search Quality
     - Best For
   * - **Gemini Flash**
     - ⚡⚡⚡
     - 💰
     - ✅✅✅
     - Academic research, fact-finding
   * - **Grok-3-mini**
     - ⚡⚡
     - 💰💰
     - ✅✅✅✅
     - Current events, news, trends
   * - **GPT-5-nano**
     - ⚡⚡
     - 💰💰
     - ✅✅
     - General research, balanced approach
   * - **Claude Sonnet**
     - ⚡
     - 💰💰💰
     - ✅✅
     - Deep analysis, academic rigor

**Example Configuration**:

.. code-block:: yaml

   agents:
     - id: "fast_researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

     - id: "deep_analyzer"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         enable_web_search: true

Coding & Development Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Best Options**:

1. **Claude Code** - Native dev tools (Read, Write, Edit, Bash, Grep)
2. **GPT-5 with Code Interpreter** - Data analysis, calculations
3. **Gemini 2.5** - Code generation with execution

.. list-table::
   :header-rows: 1
   :widths: 20 20 20 40

   * - Backend
     - File Operations
     - Code Execution
     - Best For
   * - **Claude Code**
     - ✅✅✅✅
     - ✅✅✅
     - Full development workflow, refactoring, project generation
   * - **GPT-5**
     - Via MCP
     - ✅✅✅✅
     - Data science, calculations, analysis
   * - **Gemini**
     - Via MCP
     - ✅✅✅
     - Quick scripts, prototyping
   * - **AG2**
     - ✅✅✅
     - ✅✅✅✅
     - Complex multi-step coding with execution

**Example Configuration**:

.. code-block:: yaml

   agents:
     - id: "developer"
       backend:
         type: "claude_code"
         cwd: "project_workspace"
         disallowed_tools: ["Bash(rm*)", "Bash(sudo*)"]

     - id: "reviewer"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"

File Operations & Project Work
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Best Options**:

1. **Claude Code** - Best file operations, native tools
2. **Any backend + MCP Filesystem** - Universal file access
3. **AG2 with Docker execution** - Isolated environment

.. list-table::
   :header-rows: 1
   :widths: 20 15 15 15 35

   * - Backend
     - Setup
     - Safety
     - Speed
     - Best For
   * - **Claude Code**
     - Easy
     - ✅✅✅✅
     - ⚡⚡⚡
     - Project generation, refactoring
   * - **Gemini + MCP**
     - Medium
     - ✅✅✅
     - ⚡⚡
     - Multi-agent file collaboration
   * - **GPT-5 + MCP**
     - Medium
     - ✅✅✅
     - ⚡⚡
     - Complex file workflows
   * - **AG2 + Docker**
     - Complex
     - ✅✅✅✅✅
     - ⚡
     - Maximum isolation, security

**Example Configuration**:

.. code-block:: yaml

   agents:
     - id: "file_manager"
       backend:
         type: "claude_code"
         cwd: "workspace1"

     - id: "analyzer"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         mcp_servers:
           - name: "filesystem"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-filesystem", "."]

   orchestrator:
     coordination:
       enable_planning_mode: true  # Prevent conflicts

Multi-Agent Coordination
~~~~~~~~~~~~~~~~~~~~~~~~

**Best Options**:

1. **Mixed team**: Gemini (fast) + GPT-5 (reasoning) + Claude (quality)
2. **Budget team**: 3-5x Gemini Flash
3. **Power team**: GPT-5 + Claude Sonnet + Grok

.. list-table::
   :header-rows: 1
   :widths: 30 20 20 30

   * - Team Composition
     - Cost/Query
     - Quality
     - Best For
   * - **5x Gemini Flash**
     - 💰
     - ✅✅✅
     - Fast iteration, testing
   * - **Gemini + GPT + Claude**
     - 💰💰💰
     - ✅✅✅✅
     - Production, high quality
   * - **GPT-5 + Sonnet + Grok**
     - 💰💰💰💰
     - ✅✅✅✅✅
     - Maximum quality, critical tasks
   * - **3x GPT-5-nano**
     - 💰💰
     - ✅✅✅
     - Balanced approach

**Example Configuration**:

.. code-block:: yaml

   agents:
     - id: "fast_explorer"
       backend: {type: "gemini", model: "gemini-2.5-flash"}

     - id: "deep_thinker"
       backend: {type: "openai", model: "gpt-5-nano"}

     - id: "quality_check"
       backend: {type: "claude", model: "claude-sonnet-4"}

Cost Optimization
~~~~~~~~~~~~~~~~~

**Ultra-Low Cost** (< $0.10/query):

* 3x Gemini Flash
* GPT-5-nano
* LM Studio (free, local)

**Balanced** ($0.50-2.00/query):

* Mix of Flash models + one premium model
* Gemini + GPT-5-nano combo

**Premium** ($2.00+/query):

* Claude Sonnet + GPT-5 + Grok
* Multiple premium models

Backend Feature Comparison
---------------------------

Planning Mode Compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Backend
     - Planning Mode
     - Notes
   * - **Gemini**
     - ✅✅✅✅
     - Excellent instruction following for planning
   * - **GPT-4/5**
     - ✅✅✅✅
     - Strong adherence to planning instructions
   * - **Claude**
     - ✅✅✅✅
     - Highly reliable instruction following
   * - **Claude Code**
     - ✅✅✅✅
     - Native tool control + planning
   * - **Grok**
     - ✅✅✅
     - Good instruction following
   * - **LM Studio**
     - ⚠️ Varies
     - Depends on local model quality

MCP Tool Integration
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Backend
     - MCP Support
     - Notes
   * - **Gemini**
     - ✅✅✅✅
     - Full MCP + planning mode support
   * - **GPT/OpenAI**
     - ✅✅✅✅
     - Full MCP integration
   * - **Claude**
     - ✅✅✅✅
     - Full MCP support
   * - **Claude Code**
     - ✅✅✅✅
     - MCP + native tools
   * - **Grok**
     - ✅✅✅
     - Good MCP support
   * - **Azure OpenAI**
     - ❌
     - Limited/no MCP support
   * - **ChatCompletion**
     - ⚠️ Varies
     - Depends on provider

Speed & Response Time
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Backend
     - Typical Speed
     - Notes
   * - **Gemini Flash**
     - ⚡⚡⚡⚡
     - Fastest for most tasks
   * - **GPT-5-nano**
     - ⚡⚡⚡
     - Fast with good quality
   * - **Grok-3-mini**
     - ⚡⚡⚡
     - Quick responses
   * - **Claude Sonnet**
     - ⚡⚡
     - Slower but thorough
   * - **GPT-5**
     - ⚡⚡
     - Balanced speed/quality
   * - **LM Studio**
     - ⚡ (varies)
     - Depends on local hardware

Specialized Use Cases
---------------------

Real-Time Information
~~~~~~~~~~~~~~~~~~~~~

**Best**: Grok-3 with Live Search

.. code-block:: yaml

   backend:
     type: "grok"
     model: "grok-3-mini"
     enable_web_search: true

**Why**: Grok's Live Search is optimized for current events, news, and real-time data.

**Example**: "What are today's major tech announcements?"

Academic Research
~~~~~~~~~~~~~~~~~

**Best**: Gemini 2.5 Flash + Claude Sonnet 4

.. code-block:: yaml

   agents:
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

     - id: "reviewer"
       backend:
         type: "claude"
         model: "claude-sonnet-4"

**Why**: Gemini for broad search, Claude for deep analysis and quality control.

**Example**: "Research the latest developments in quantum computing"

Data Analysis
~~~~~~~~~~~~~

**Best**: GPT-5 with Code Interpreter

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-5-nano"
     enable_code_interpreter: true

**Why**: Code Interpreter provides sandboxed Python execution for data analysis.

**Example**: "Analyze this CSV and create visualizations"

Project Generation
~~~~~~~~~~~~~~~~~~

**Best**: Claude Code + Gemini reviewer

.. code-block:: yaml

   agents:
     - id: "builder"
       backend:
         type: "claude_code"
         cwd: "project_workspace"

     - id: "reviewer"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"

   orchestrator:
     coordination:
       enable_planning_mode: true

**Why**: Claude Code for file operations, Gemini for quick review, planning mode prevents conflicts.

**Example**: "Create a FastAPI microservice with tests and documentation"

Content Creation
~~~~~~~~~~~~~~~~

**Best**: Claude Sonnet + GPT-5 + Gemini (3-agent team)

.. code-block:: yaml

   agents:
     - id: "writer"
       backend: {type: "claude", model: "claude-sonnet-4"}

     - id: "editor"
       backend: {type: "openai", model: "gpt-5-nano"}

     - id: "reviewer"
       backend: {type: "gemini", model: "gemini-2.5-flash"}

**Why**: Multiple perspectives, voting produces best content.

**Example**: "Write a comprehensive blog post about AI safety"

Enterprise Deployments
~~~~~~~~~~~~~~~~~~~~~~

**Best**: Azure OpenAI

.. code-block:: yaml

   backend:
     type: "azure_openai"
     model: "gpt-4"
     endpoint: "https://your-resource.openai.azure.com/"
     api_version: "2024-02-15-preview"

**Why**: Enterprise features, compliance, data residency.

Local/Offline Development
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Best**: LM Studio

.. code-block:: yaml

   backend:
     type: "lmstudio"
     model: "your-local-model"
     base_url: "http://localhost:1234/v1"

**Why**: No API costs, privacy, offline capability.

Common Mistakes & Solutions
---------------------------

Mistake 1: Using Premium Models for Simple Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Using GPT-5 or Claude Sonnet for "What is 2+2?"

**Solution**: Use fast, cheap models (Gemini Flash, GPT-5-nano) for simple tasks.

.. code-block:: bash

   # ❌ Expensive
   uv run python -m massgen.cli --model claude-sonnet-4 "What is 2+2?"

   # ✅ Cost-effective
   uv run python -m massgen.cli --model gemini-2.5-flash "What is 2+2?"

Mistake 2: Not Using Planning Mode with File Operations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Multiple agents modifying files during coordination.

**Solution**: Always enable planning mode for file operations.

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true  # ← Essential for file ops

Mistake 3: Wrong Backend for Use Case
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Using Claude Code without file operations, or Grok without web search.

**Solution**: Match backend strengths to your needs:

* Need files? → Claude Code
* Need speed? → Gemini Flash
* Need real-time data? → Grok
* Need code execution? → GPT with Code Interpreter

Mistake 4: All Agents Same Model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: 5x identical agents (less diversity).

**Solution**: Mix different models for varied perspectives:

.. code-block:: yaml

   agents:
     - backend: {type: "gemini", model: "gemini-2.5-flash"}
     - backend: {type: "openai", model: "gpt-5-nano"}
     - backend: {type: "claude", model: "claude-sonnet-4"}

Mistake 5: Not Using MCP When Needed
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Trying to access external services without MCP.

**Solution**: Use MCP servers for external tools:

.. code-block:: yaml

   backend:
     mcp_servers:
       - name: "weather"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-weather"]

Migration Guide
---------------

From Single Backend to Multi-Agent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Step 1**: Start with your current backend:

.. code-block:: yaml

   agent:
     backend: {type: "openai", model: "gpt-4o"}

**Step 2**: Add complementary agents:

.. code-block:: yaml

   agents:
     - id: "primary"
       backend: {type: "openai", model: "gpt-4o"}
     - id: "fast_review"
       backend: {type: "gemini", model: "gemini-2.5-flash"}

**Step 3**: Enable coordination:

.. code-block:: yaml

   agents:
     - id: "primary"
       backend: {type: "openai", model: "gpt-4o"}
     - id: "fast_review"
       backend: {type: "gemini", model: "gemini-2.5-flash"}
     - id: "quality_check"
       backend: {type: "claude", model: "claude-sonnet-4"}

   ui:
     display_type: "rich_terminal"

From Local to Cloud
~~~~~~~~~~~~~~~~~~~

**LM Studio** → **Gemini Flash** (cost-effective cloud):

.. code-block:: yaml

   # Before (local)
   backend: {type: "lmstudio", model: "local-model"}

   # After (cloud)
   backend: {type: "gemini", model: "gemini-2.5-flash"}

From Basic to File Operations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Add MCP filesystem** to any backend:

.. code-block:: yaml

   backend:
     type: "gemini"  # or any backend
     model: "gemini-2.5-flash"
     mcp_servers:
       - name: "filesystem"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-filesystem", "."]

Related Documentation
---------------------

* :doc:`supported_models` - Complete technical specifications
* :doc:`../user_guide/backends` - Backend configuration details
* :doc:`../user_guide/planning_mode` - Planning mode for file operations
* :doc:`../user_guide/mcp_integration` - MCP tool integration
* :doc:`yaml_schema` - Complete YAML reference

Next Steps
----------

1. **Identify your primary use case** from the list above
2. **Choose your backend(s)** based on the recommendations
3. **Start with a simple configuration** and iterate
4. **Monitor costs and performance** to optimize
5. **Scale to multi-agent** when you need diverse perspectives
