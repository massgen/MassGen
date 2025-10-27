Backend Configuration
=====================

Backends connect MassGen agents to AI model providers. Each backend is configured in YAML and provides specific capabilities like web search, code execution, and file operations.

Overview
--------

Each agent in MassGen requires a backend configuration that specifies:

* **Provider**: Which AI service to use (OpenAI, Claude, Gemini, etc.)
* **Model**: Which specific model within that provider
* **Capabilities**: Which built-in tools are enabled
* **Parameters**: Model settings like temperature, max_tokens, etc.

Available Backends
------------------

Backend Types
~~~~~~~~~~~~~

MassGen supports these backend types (configured via ``type`` field in YAML):

.. list-table::
   :header-rows: 1
   :widths: 20 30 50

   * - Backend Type
     - Provider
     - Models
   * - ``openai``
     - OpenAI
     - GPT-5, GPT-5-mini, GPT-5-nano, GPT-4, GPT-4o
   * - ``claude``
     - Anthropic
     - Claude Haiku 3.5, Claude Sonnet 4, Claude Opus 4
   * - ``claude_code``
     - Anthropic (SDK)
     - Claude Sonnet 4, Claude Opus 4 (with dev tools)
   * - ``gemini``
     - Google
     - Gemini 2.5 Flash, Gemini 2.5 Pro
   * - ``grok``
     - xAI
     - Grok-4, Grok-3, Grok-3-mini
   * - ``azure_openai``
     - Microsoft Azure
     - GPT-4, GPT-4o, GPT-5 (Azure deployments)
   * - ``zai``
     - ZhipuAI
     - GLM-4.5
   * - ``ag2``
     - AG2 Framework
     - Any AG2-compatible agent
   * - ``lmstudio``
     - LM Studio
     - Local open-source models
   * - ``chatcompletion``
     - Generic
     - Any OpenAI-compatible API

Backend Capabilities
~~~~~~~~~~~~~~~~~~~~

Different backends support different built-in tools:

.. list-table:: Backend Tool Support
   :header-rows: 1
   :widths: 15 10 10 10 10 12 12 12 10 10

   * - Backend
     - Web Search
     - Code Execution
     - Bash/Shell
     - Image
     - Audio
     - Video
     - MCP Support
     - Filesystem
     - Custom Tools
   * - ``openai``
     - ⭐
     - ⭐
     - ✅
     - ⭐ Both
     - ⭐ Both
     - ⭐ Generation
     - ✅
     - ✅
     - ✅
   * - ``claude``
     - ⭐
     - ⭐
     - ✅
     - 🔧
     - 🔧
     - 🔧
     - ✅
     - ✅
     - ✅
   * - ``claude_code``
     - ⭐
     - ❌
     - ⭐
     - 🔧
     - 🔧
     - 🔧
     - ✅
     - ⭐
     - ✅
   * - ``gemini``
     - ⭐
     - ⭐
     - ✅
     - 🔧
     - 🔧
     - 🔧
     - ✅
     - ✅
     - ✅
   * - ``grok``
     - ⭐
     - ❌
     - ✅
     - 🔧
     - 🔧
     - 🔧
     - ✅
     - ✅
     - ✅
   * - ``azure_openai``
     - ⭐
     - ⭐
     - ✅
     - ⭐ Both
     - ❌
     - ❌
     - ✅
     - ✅
     - ❌
   * - ``chatcompletion``
     - ❌
     - ❌
     - ✅
     - 🔧
     - 🔧
     - 🔧
     - ✅
     - ✅
     - ✅
   * - ``lmstudio``
     - ❌
     - ❌
     - ✅
     - 🔧
     - 🔧
     - 🔧
     - ✅
     - ✅
     - ✅
   * - ``inference``
     - ❌
     - ❌
     - ✅
     - 🔧
     - 🔧
     - 🔧
     - ✅
     - ✅
     - ✅
   * - ``ag2``
     - ❌
     - ⭐
     - ❌
     - ❌
     - ❌
     - ❌
     - ❌
     - ❌
     - ❌

**Notes:**

* **Symbol Legend:**

  * ⭐ **Built-in** - Native backend feature (e.g., Anthropic's web search, OpenAI's native image API, Claude Code's Bash tool)
  * 🔧 **Via Custom Tools** - Available through custom tools (requires ``OPENAI_API_KEY`` for multimodal understanding)
  * ✅ **MCP-based or Available** - Feature available via MCP integration or standard capability
  * ❌ **Not available** - Feature not supported

* **Custom Tools:**

  * Custom tools allow you to give agents access to your own Python functions
  * Most backends support custom tools (OpenAI, Claude, Claude Code, Gemini, Grok, Chat Completions, LM Studio, Inference)
  * **Azure OpenAI** and **AG2** do not support custom tools as they inherit from the base backend class without the custom tools layer
  * Custom tools are essential for multimodal understanding features (``understand_image``, ``understand_video``, ``understand_audio``, ``understand_file``)
  * See :doc:`custom_tools` for complete documentation on creating and using custom tools

* **Code Execution vs Bash/Shell:**

  * **Code Execution (⭐)**: Backend provider's native code execution tool (no access to MassGen workspaces)

    * ``openai``: OpenAI code interpreter for calculations and data analysis
    * ``claude``: Anthropic's code execution tool
    * ``gemini``: Google's code execution tool
    * ``azure_openai``: Azure OpenAI code interpreter
    * ``ag2``: AG2 framework code executors (Local, Docker, Jupyter, Cloud)

  * **Bash/Shell**: (MassGen-level feature, will directly access workspaces)

    * ⭐ (``claude_code`` only): Native Bash tool built into Claude Code
    * ✅ (all MCP-enabled backends): Universal bash/shell via ``enable_mcp_command_line: true``
    * See :doc:`code_execution` for detailed setup and comparison

  * **You can use both**: Backends can use built-in code execution AND MCP-based bash/shell simultaneously, though it is preferred to choose one. Use built-in code execution for isolated tasks, and MCP bash/shell for operations you want to affect the agent's workspace.

* **Filesystem:**

  * ⭐ (``claude_code`` only): Native filesystem tools (Read, Write, Edit, Bash, Grep, Glob)
  * ✅ (all backends with ``cwd`` parameter): Filesystem operations handled automatically through workspace configuration
  * See :doc:`file_operations` for detailed filesystem configuration

* **Multimodal Capabilities:**

  * **⭐ Native Multimodal Support**: The backend/model API directly handles multimodal content

    * **⭐ Both** (e.g., ``openai``, ``azure_openai``): Native API supports BOTH understanding (analyze) AND generation (create)
    * **⭐ Generation** (e.g., ``openai`` video): Can create videos via Sora-2 API but not analyze them

  * **🔧 Via Custom Tools**: Multimodal understanding through custom tools (``understand_image``, ``understand_video``, ``understand_audio``)

    * Works with any backend that supports custom tools
    * Requires ``OPENAI_API_KEY`` in ``.env`` file (tools use OpenAI's API for processing)
    * Examples: ``claude``, ``claude_code``, ``gemini``, ``grok``, ``chatcompletion``, ``lmstudio``, ``inference``
    * Does NOT work with ``azure_openai`` or ``ag2`` (these backends don't support custom tools)
    * See :doc:`multimodal` for complete setup instructions

  * **Understanding vs Generation**:

    * **Understanding**: Analyze existing content (images, audio, video)
    * **Generation**: Create new content from text prompts
    * **Both**: Supports both understanding AND generation

See :doc:`../reference/supported_models` for the complete backend capabilities reference.

Configuring Backends
--------------------

Basic Backend Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every agent needs a ``backend`` section in the YAML configuration:

.. code-block:: yaml

   agents:
     - id: "my_agent"
       backend:
         type: "openai"          # Backend type (required)
         model: "gpt-5-nano"     # Model name (required)

Backend-Specific Examples
-------------------------

OpenAI Backend
~~~~~~~~~~~~~~

**Basic Configuration:**

.. code-block:: yaml

   agents:
     - id: "gpt_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         enable_web_search: true
         enable_code_interpreter: true

**With Reasoning Parameters:**

.. code-block:: yaml

   agents:
     - id: "reasoning_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         text:
           verbosity: "medium"      # low, medium, high
         reasoning:
           effort: "high"            # low, medium, high
           summary: "auto"           # auto, concise, detailed

**Supported Models:** GPT-5, GPT-5-mini, GPT-5-nano, GPT-4, GPT-4o, GPT-4-turbo, GPT-3.5-turbo

Claude Backend
~~~~~~~~~~~~~~

**Basic Configuration:**

.. code-block:: yaml

   agents:
     - id: "claude_agent"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         enable_web_search: true
         enable_code_interpreter: true

**With MCP Integration:**

.. code-block:: yaml

   agents:
     - id: "claude_mcp"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         mcp_servers:
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-weather"]

**Supported Models:** claude-haiku-4-5-20251001, claude-sonnet-4-5-20250929, claude-opus-4-1-20250805, claude-sonnet-4-20250514, claude-3-5-sonnet-latest, claude-3-5-haiku-latest

Claude Code Backend
~~~~~~~~~~~~~~~~~~~

**With Workspace Configuration:**

.. code-block:: yaml

   agents:
     - id: "code_agent"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"           # Working directory for file operations

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

**Special Features:**

* Native file operations (Read, Write, Edit, Bash, Grep, Glob)
* Workspace isolation
* Snapshot sharing between agents
* Full development tool suite

Gemini Backend
~~~~~~~~~~~~~~

**Basic Configuration:**

.. code-block:: yaml

   agents:
     - id: "gemini_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true
         enable_code_execution: true

**With Safety Settings:**

.. code-block:: yaml

   agents:
     - id: "safe_gemini"
       backend:
         type: "gemini"
         model: "gemini-2.5-pro"
         safety_settings:
           HARM_CATEGORY_HARASSMENT: "BLOCK_MEDIUM_AND_ABOVE"
           HARM_CATEGORY_HATE_SPEECH: "BLOCK_MEDIUM_AND_ABOVE"

**Supported Models:** gemini-2.5-flash, gemini-2.5-pro, gemini-2.5-flash-thinking

Grok Backend
~~~~~~~~~~~~

**Basic Configuration:**

.. code-block:: yaml

   agents:
     - id: "grok_agent"
       backend:
         type: "grok"
         model: "grok-3-mini"
         enable_web_search: true

**Supported Models:** grok-4, grok-4-fast, grok-3, grok-3-mini

Azure OpenAI Backend
~~~~~~~~~~~~~~~~~~~~

**Configuration:**

.. code-block:: yaml

   agents:
     - id: "azure_agent"
       backend:
         type: "azure_openai"
         model: "gpt-4"
         deployment_name: "my-gpt4-deployment"
         api_version: "2024-02-15-preview"

**Required Environment Variables:**

.. code-block:: bash

   AZURE_OPENAI_API_KEY=...
   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   AZURE_OPENAI_API_VERSION=YOUR-AZURE-OPENAI-API-VERSION

AG2 Backend
~~~~~~~~~~~

**Configuration:**

.. code-block:: yaml

   agents:
     - id: "ag2_agent"
       backend:
         type: "ag2"
         agent_type: "ConversableAgent"
         llm_config:
           config_list:
             - model: "gpt-4"
               api_key: "${OPENAI_API_KEY}"
         code_execution_config:
           executor: "local"
           work_dir: "coding"

See :doc:`ag2_integration` for detailed AG2 configuration.

LM Studio Backend
~~~~~~~~~~~~~~~~~

**For Local Models:**

.. code-block:: yaml

   agents:
     - id: "local_agent"
       backend:
         type: "lmstudio"
         model: "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF"
         port: 1234

**Features:**

* Automatic LM Studio CLI installation
* Auto-download and loading of models
* Zero-cost usage
* Full privacy (local inference)

Local Inference Backends (vLLM & SGLang)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Unified Inference Backend** (v0.0.24-v0.0.25)

MassGen supports high-performance local model serving through vLLM and SGLang with automatic server detection:

.. code-block:: yaml

   agents:
     - id: "local_vllm"
       backend:
         type: "chatcompletion"
         model: "meta-llama/Llama-3.1-8B-Instruct"
         base_url: "http://localhost:8000/v1"    # vLLM default port
         api_key: "EMPTY"

     - id: "local_sglang"
       backend:
         type: "chatcompletion"
         model: "meta-llama/Llama-3.1-8B-Instruct"
         base_url: "http://localhost:30000/v1"   # SGLang default port
         api_key: "${SGLANG_API_KEY}"

**Auto-Detection:**

* **vLLM**: Default port 8000
* **SGLang**: Default port 30000
* Automatically detects server type based on configuration
* Unified InferenceBackend class handles both

**SGLang-Specific Parameters:**

.. code-block:: yaml

   backend:
     type: "chatcompletion"
     model: "meta-llama/Llama-3.1-8B-Instruct"
     base_url: "http://localhost:30000/v1"
     separate_reasoning: true        # SGLang guided generation
     top_k: 50                        # Sampling parameter
     repetition_penalty: 1.1          # Prevent repetition

**Mixed Deployments:**

Run both vLLM and SGLang simultaneously:

.. code-block:: yaml

   agents:
     - id: "vllm_agent"
       backend:
         type: "chatcompletion"
         model: "Qwen/Qwen2.5-7B-Instruct"
         base_url: "http://localhost:8000/v1"
         api_key: "EMPTY"

     - id: "sglang_agent"
       backend:
         type: "chatcompletion"
         model: "Qwen/Qwen2.5-7B-Instruct"
         base_url: "http://localhost:30000/v1"
         api_key: "${SGLANG_API_KEY}"
         separate_reasoning: true

**Benefits of Local Inference:**

* **Cost Savings**: Zero API costs after initial setup
* **Privacy**: No data sent to external services
* **Control**: Full control over model selection and parameters
* **Performance**: Optimized for high-throughput inference
* **Customization**: Fine-tune models for specific use cases

**Setup vLLM Server:**

.. code-block:: bash

   # Install vLLM
   pip install vllm

   # Start vLLM server
   vllm serve meta-llama/Llama-3.1-8B-Instruct \
     --host 0.0.0.0 \
     --port 8000

**Setup SGLang Server:**

.. code-block:: bash

   # Install SGLang
   pip install "sglang[all]"

   # Start SGLang server
   python -m sglang.launch_server \
     --model-path meta-llama/Llama-3.1-8B-Instruct \
     --host 0.0.0.0 \
     --port 30000

**Configuration Example:**

See ``@examples/basic/multi/two_qwen_vllm_sglang.yaml`` for a complete mixed deployment example.

Common Backend Parameters
-------------------------

Model Parameters
~~~~~~~~~~~~~~~~

All backends support these common parameters:

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-5-nano"

     # Generation parameters
     temperature: 0.7           # Randomness (0.0-2.0, default 0.7)
     max_tokens: 4096           # Maximum response length
     top_p: 1.0                 # Nucleus sampling (0.0-1.0)

     # API configuration
     api_key: "${OPENAI_API_KEY}"  # Optional - uses env var by default
     timeout: 60                    # Request timeout in seconds

Tool Configuration
~~~~~~~~~~~~~~~~~~

Enable or disable built-in tools:

.. code-block:: yaml

   backend:
     type: "gemini"
     model: "gemini-2.5-flash"

     # Enable tools
     enable_web_search: true
     enable_code_execution: true

     # MCP servers (see MCP Integration guide)
     mcp_servers:
       - name: "server_name"
         type: "stdio"
         command: "npx"
         args: ["..."]

Multi-Backend Configurations
-----------------------------

Using Different Backends
~~~~~~~~~~~~~~~~~~~~~~~~

Each agent can use a different backend:

.. code-block:: yaml

   agents:
     - id: "fast_researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

     - id: "deep_analyst"
       backend:
         type: "openai"
         model: "gpt-5"
         reasoning:
           effort: "high"

     - id: "code_expert"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"

This is the **recommended approach** - use each backend's strengths:

* **Gemini 2.5 Flash**: Fast research with web search
* **GPT-5**: Advanced reasoning and analysis
* **Claude Code**: Development with file operations

Backend Selection Guide
-----------------------

Choosing the Right Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~

Consider these factors when selecting backends:

**For Research Tasks:**

* **Gemini 2.5 Flash**: Fast, cost-effective, excellent web search
* **GPT-5-nano**: Good reasoning with web search
* **Grok**: Real-time information access

**For Coding Tasks:**

* **Claude Code**: Best for file operations, full dev tools
* **GPT-5**: Advanced code generation with reasoning
* **Gemini 2.5 Pro**: Complex code analysis

**For Analysis Tasks:**

* **GPT-5**: Deep reasoning and complex analysis
* **Claude Sonnet 4**: Long context, detailed analysis
* **Gemini 2.5 Pro**: Comprehensive multimodal analysis

**For Cost-Sensitive Tasks:**

* **GPT-5-nano**: Low-cost OpenAI model
* **Grok-3-mini**: Fast and affordable
* **Gemini 2.5 Flash**: Very cost-effective
* **LM Studio**: Free (local inference)

**For Privacy-Sensitive Tasks:**

* **LM Studio**: Fully local, no data sharing
* **Azure OpenAI**: Enterprise security
* **Self-hosted vLLM**: Private cloud deployment

Backend Configuration Best Practices
-------------------------------------

1. **Start with defaults**: Test with default parameters before tuning
2. **Use environment variables**: Never hardcode API keys
3. **Match backend to task**: Use each backend's strengths
4. **Enable only needed tools**: Disable unused capabilities
5. **Set appropriate timeouts**: Longer timeouts for complex tasks
6. **Monitor costs**: Track API usage across backends
7. **Test configurations**: Verify settings before production use

Advanced Backend Configuration
-------------------------------

For detailed backend-specific parameters, see:

* `Backend Configuration Guide <https://github.com/Leezekun/MassGen/blob/main/@examples/BACKEND_CONFIGURATION.md>`_
* :doc:`../reference/yaml_schema` - Complete YAML schema

MCP Integration
~~~~~~~~~~~~~~~

See :doc:`mcp_integration` for:

* Adding MCP servers to backends
* Tool filtering (allowed_tools, exclude_tools)
* Planning mode configuration (v0.0.29)
* HTTP-based MCP servers

File Operations
~~~~~~~~~~~~~~~

See :doc:`file_operations` for:

* Workspace configuration
* Snapshot storage
* Permission management
* Cross-agent file sharing

Troubleshooting
---------------

**Backend not found:**

Ensure the backend type is correct:

.. code-block:: bash

   # Correct backend types
   type: "openai"         # ✅
   type: "claude_code"    # ✅
   type: "gemini"         # ✅

   # Incorrect (common mistakes)
   type: "gpt"            # ❌ Use "openai"
   type: "claude"         # ✅ (but consider "claude_code" for dev tools)
   type: "google"         # ❌ Use "gemini"

**API key not found:**

Check your ``.env`` file has the correct variable name:

.. code-block:: bash

   # Backend type → Environment variable
   openai       → OPENAI_API_KEY
   claude       → ANTHROPIC_API_KEY
   gemini       → GOOGLE_API_KEY
   grok         → XAI_API_KEY
   azure_openai → AZURE_OPENAI_API_KEY

**Model not supported:**

Verify the model name matches the backend's supported models:

.. code-block:: yaml

   # Check supported models in README.md or use --model flag
   backend:
     type: "openai"
     model: "gpt-5-nano"  # ✅ Supported
     model: "gpt-6"       # ❌ Not yet available

Next Steps
----------

* :doc:`../quickstart/configuration` - Full configuration guide
* :doc:`mcp_integration` - Add external tools via MCP
* :doc:`file_operations` - Enable file system operations
* :doc:`../reference/supported_models` - Complete model list
* :doc:`../examples/basic_examples` - See backends in action
