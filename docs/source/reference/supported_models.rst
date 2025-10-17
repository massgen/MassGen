Supported Models & Backends
============================

MassGen supports a wide range of LLM providers and models. This page provides comprehensive information about backend types, model support, and setup requirements.

Quick Reference: Backend Setup
--------------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Backend Type
     - Setup Requirements
   * - **Claude API**
     - ``ANTHROPIC_API_KEY``
   * - **Claude Code**
     - Native tools: Read, Write, Edit, Bash, Grep, Glob, TodoWrite. If logged in via Anthropic account, ``ANTHROPIC_API_KEY`` is NOT needed (comment it out in ``.env`` or it will default to using the API key)
   * - **Gemini API**
     - ``GEMINI_API_KEY``
   * - **OpenAI API**
     - ``OPENAI_API_KEY``
   * - **Grok API**
     - ``XAI_API_KEY``
   * - **Azure OpenAI**
     - Azure deployment config: ``AZURE_OPENAI_API_KEY``, ``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_API_VERSION``
   * - **Z AI**
     - ``ZAI_API_KEY``
   * - **ChatCompletion**
     - ``base_url`` + provider-specific API key (e.g., ``CEREBRAS_API_KEY``, ``TOGETHER_API_KEY``)
   * - **LM Studio**
     - Local LM Studio server running
   * - **vLLM/SGLang**
     - Local inference server on port 8000 (vLLM) or 30000 (SGLang)
   * - **AG2 Framework**
     - AG2 installation + LLM API keys for chosen provider

**For detailed backend capabilities (web search, code execution, MCP support), see:** :doc:`../user_guide/backends`

API-Based Models
----------------

Azure OpenAI
~~~~~~~~~~~~

.. list-table::
   :widths: 40 60

   * - **Models**
     - GPT-4, GPT-4o, GPT-3.5-turbo, GPT-4.1, GPT-5-chat
   * - **Backend Type**
     - ``azure_openai``
   * - **Tools Support**
     - Code interpreter, Azure deployment management
   * - **MCP Support**
     - ❌ Not yet supported

Claude (Anthropic)
~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 40 60

   * - **Models**
     - Haiku 3.5, Sonnet 4, Opus 4 series
   * - **Backend Type**
     - ``claude``
   * - **Tools Support**
     - ✅ Web search, code execution, file operations
   * - **MCP Support**
     - ✅ Full integration

Claude Code
~~~~~~~~~~~

.. list-table::
   :widths: 40 60

   * - **Models**
     - Native Claude Code SDK
   * - **Backend Type**
     - ``claude_code``
   * - **Tools Support**
     - ✅ **Native dev tools**: Read, Write, Edit, Bash, Grep, Glob, TodoWrite
   * - **MCP Support**
     - ✅ Full integration

Gemini (Google)
~~~~~~~~~~~~~~~

.. list-table::
   :widths: 40 60

   * - **Models**
     - Gemini 2.5 Flash, Gemini 2.5 Pro series
   * - **Backend Type**
     - ``gemini``
   * - **Tools Support**
     - ✅ Web search, code execution, file operations
   * - **MCP Support**
     - ✅ Full integration with planning mode

Grok (xAI)
~~~~~~~~~~

.. list-table::
   :widths: 40 60

   * - **Models**
     - Grok-4, Grok-3, Grok-3-mini series
   * - **Backend Type**
     - ``grok``
   * - **Tools Support**
     - ✅ Web search, file operations
   * - **MCP Support**
     - ✅ Full integration

OpenAI
~~~~~~

.. list-table::
   :widths: 40 60

   * - **Models**
     - GPT-5, GPT-5-mini, GPT-5-nano, GPT-4 series
   * - **Backend Type**
     - ``openai``
   * - **Tools Support**
     - ✅ Web search, code interpreter, file operations
   * - **MCP Support**
     - ✅ Full integration

Z AI
~~~~

.. list-table::
   :widths: 40 60

   * - **Models**
     - GLM-4.5
   * - **Backend Type**
     - ``zai``
   * - **Tools Support**
     - File operations
   * - **MCP Support**
     - ✅ Integration available

ChatCompletion (Generic OpenAI-Compatible)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``chatcompletion`` backend provides a generic way to connect to any OpenAI-compatible API endpoint. This is the most flexible backend type and works with many providers.

.. list-table::
   :widths: 40 60

   * - **Backend Type**
     - ``chatcompletion``
   * - **Compatible Providers**
     - Cerebras AI, Together AI, Fireworks AI, Groq, OpenRouter, POE, and any OpenAI-compatible API
   * - **Required Config**
     - ``base_url`` pointing to the provider's API endpoint
   * - **API Key**
     - Provider-specific (e.g., ``CEREBRAS_API_KEY``, ``TOGETHER_API_KEY``)
   * - **MCP Support**
     - ✅ Full integration
   * - **Tools Support**
     - Depends on provider's function calling support

**Configuration Example:**

.. code-block:: yaml

   backend:
     type: "chatcompletion"
     model: "gpt-oss-120b"              # Model name
     base_url: "https://api.cerebras.ai/v1"  # Provider endpoint
     api_key: "${CEREBRAS_API_KEY}"    # Provider API key
     temperature: 0.7
     max_tokens: 2000
     mcp_servers:                       # Optional MCP tools
       - name: "weather"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-weather"]

**Supported Providers:**

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Provider
     - Base URL
     - Environment Variable
   * - **Cerebras AI**
     - ``https://api.cerebras.ai/v1``
     - ``CEREBRAS_API_KEY``
   * - **Together AI**
     - ``https://api.together.xyz/v1``
     - ``TOGETHER_API_KEY``
   * - **Fireworks AI**
     - ``https://api.fireworks.ai/inference/v1``
     - ``FIREWORKS_API_KEY``
   * - **Groq**
     - ``https://api.groq.com/openai/v1``
     - ``GROQ_API_KEY``
   * - **OpenRouter**
     - ``https://openrouter.ai/api/v1``
     - ``OPENROUTER_API_KEY``
   * - **Kimi/Moonshot**
     - ``https://api.moonshot.cn/v1``
     - ``MOONSHOT_API_KEY``
   * - **Nebius AI Studio**
     - Provider-specific
     - ``NEBIUS_API_KEY``
   * - **POE**
     - Platform-specific
     - Platform credentials

**Common Models:**

* **Cerebras**: ``gpt-oss-120b``, ``gpt-oss-70b``
* **Together AI**: ``meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo``, ``mistralai/Mixtral-8x7B-Instruct-v0.1``
* **Fireworks AI**: ``accounts/fireworks/models/llama-v3p1-405b-instruct``
* **Groq**: ``llama-3.1-70b-versatile``, ``mixtral-8x7b-32768``

Tool Enablement Reference
--------------------------

This section shows exactly which configuration parameters work with which backends.

Backend-Level Tool Parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 20 20 20 20

   * - Backend
     - ``enable_web_search``
     - ``enable_code_execution``
     - ``enable_code_interpreter``
     - Notes
   * - **claude**
     - ✅
     - ✅
     - ❌
     - Built-in tools via Anthropic API
   * - **claude_code**
     - N/A
     - N/A
     - N/A
     - Native tools always available: Read, Write, Edit, Bash, Grep, Glob, TodoWrite. Control via ``allowed_tools`` or ``disallowed_tools``
   * - **gemini**
     - ✅
     - ✅
     - ❌
     - Google Search and code execution tools
   * - **openai**
     - ✅
     - ❌
     - ✅
     - Web search via Responses API, code interpreter for calculations
   * - **grok**
     - ✅
     - ❌
     - ❌
     - Built-in Live Search feature
   * - **azure_openai**
     - ❌
     - ❌
     - ❌
     - Limited tool support
   * - **zai**
     - ❌
     - ❌
     - ❌
     - Basic file operations only
   * - **chatcompletion**
     - Varies
     - Varies
     - Varies
     - Depends on provider (Cerebras, Together AI, etc.)
   * - **lmstudio**
     - ❌
     - ❌
     - ❌
     - Local models, tool support varies
   * - **vllm**
     - ❌
     - ❌
     - ❌
     - Local inference server
   * - **sglang**
     - ❌
     - ❌
     - ❌
     - Local inference server
   * - **ag2**
     - N/A
     - N/A
     - N/A
     - Uses AG2 code execution config

MCP Backend Parameters
~~~~~~~~~~~~~~~~~~~~~~

These parameters are available for all backends with MCP support (Claude, Gemini, OpenAI, Grok, ChatCompletion, etc.).

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Type
     - Description & Usage
   * - ``cwd``
     - string
     - Working directory for MCP filesystem operations. Relative or absolute path. Available for all MCP-enabled backends.
   * - ``allowed_tools``
     - list
     - Whitelist specific tools. Only listed tools will be available. Example: ``["read_file", "write_file", "list_directory"]``
   * - ``disallowed_tools``
     - list
     - Blacklist specific tools. All tools available except those listed. Example: ``["write_file", "create_directory", "move_file"]``
   * - ``exclude_tools``
     - list
     - Exclude specific MCP tools from being available to the agent. Similar to ``disallowed_tools`` for MCP servers.

Claude Code Additional Parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These parameters are specific to the Claude Code backend only.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Type
     - Description & Usage
   * - ``max_thinking_tokens``
     - integer
     - Maximum tokens for internal reasoning. Default: 8000. Increase for complex tasks.
   * - ``system_prompt``
     - string
     - Custom system prompt for the agent. Prepended to default instructions.
   * - ``permission_mode``
     - string
     - ``"bypassPermissions"`` to skip confirmation prompts (use in automation)
   * - ``disallowed_tools``
     - list
     - For Claude Code native tools (Read, Write, Edit, Bash, etc.). Default: ``["Bash(rm*)", "Bash(sudo*)", "Bash(su*)", "Bash(chmod*)", "Bash(chown*)"]``. Example to block web access: ``["Bash(rm*)", "WebSearch"]``

**Example MCP Configuration (any backend):**

.. code-block:: yaml

   backend:
     type: "gemini"  # or claude, openai, grok, etc.
     model: "gemini-2.5-flash"
     cwd: "my_project"  # File operations handled via cwd
     disallowed_tools: ["mcp__weather__set_location"]
     mcp_servers:
       - name: "weather"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-weather"]

**Example Claude Code Configuration:**

.. code-block:: yaml

   backend:
     type: "claude_code"
     model: "claude-sonnet-4-20250514"
     cwd: "my_project"
     disallowed_tools: ["Bash(rm*)", "Bash(sudo*)", "WebSearch"]
     max_thinking_tokens: 10000
     system_prompt: "You are an expert Python developer"

Local Models
------------

LM Studio
~~~~~~~~~

.. list-table::
   :widths: 40 60

   * - **Models**
     - LLaMA, Mistral, Qwen, and other open-weight models
   * - **Backend Type**
     - ``lmstudio``
   * - **Features**
     - Automatic CLI installation, auto-download, zero-cost usage
   * - **MCP Support**
     - Limited

vLLM & SGLang
~~~~~~~~~~~~~

Unified inference backend supporting both vLLM and SGLang servers.

.. list-table::
   :widths: 40 60

   * - **Port Detection**
     - Auto-detection: vLLM (8000), SGLang (30000)
   * - **Parameters**
     - Supports both vLLM and SGLang-specific params (top_k, repetition_penalty, separate_reasoning)
   * - **Mixed Deployment**
     - Can run both vLLM and SGLang servers simultaneously

External Frameworks
-------------------

AG2
~~~~~~~~~~~~~~~

.. list-table::
   :widths: 40 60

   * - **Agent Types**
     - ConversableAgent, AssistantAgent
   * - **Backend Type**
     - ``ag2``
   * - **Features**
     - Code execution (Local, Docker, Jupyter, Cloud)
   * - **LLM Support**
     - OpenAI, Azure, Anthropic, Google via AG2 config

See Also
--------

* :doc:`../user_guide/backends` - Detailed backend configuration
* :doc:`../user_guide/mcp_integration` - MCP tool setup
* :doc:`../user_guide/ag2_integration` - AG2 framework integration
* :doc:`yaml_schema` - YAML configuration reference
