========
Glossary
========

Standard terminology used throughout MassGen documentation.

.. glossary::
   :sorted:

   Agent
      An AI assistant configured with a specific backend (model) and capabilities. Agents work independently or collaborate with other agents to solve tasks.

   Backend
      The AI model provider integration (e.g., OpenAI, Claude, Gemini). Each backend connects to a specific AI service and provides access to its models.

   Claude Code
      Anthropic's development-focused AI assistant with native file operation tools (Read, Write, Edit, Bash, Grep, Glob). Backend type: ``claude_code``.

   Consensus
      Agreement among agents on the best solution. Agents reach consensus through voting and refinement during coordination phases.

   Context Path
      A shared directory that agents can access during multi-agent collaboration. Context paths have permissions (read or write) and enable project integration.

   Coordination Phase
      The period when agents observe each other's solutions and vote on the best approach. During coordination, agents can refine their answers based on others' work.

   Coordination Round
      One iteration of the coordination phase. Multiple rounds allow agents to iteratively improve solutions through observation and voting.

   Final Agent
      The agent whose solution is selected after coordination completes. This agent presents the final answer and can execute write operations to context paths.

   File Operation
      Reading, writing, editing, or deleting files in an agent's workspace or context paths. File operations require appropriate permissions.

   FileOperationTracker
      System component that enforces read-before-delete policies and tracks all file operations per agent for safety.

   LM Studio
      Local model inference tool that enables running open-weight models on your machine. Backend type: ``lmstudio``.

   MassGen
      Multi-Agent Scaling System for GenAI. A framework for running multiple AI agents collaboratively to solve complex tasks.

   MCP (Model Context Protocol)
      A protocol for integrating external tools and services with AI models. MCP servers provide tools like web search, filesystem access, or API integrations.

   MCP Planning Mode
      Coordination strategy where agents plan tool usage without execution during coordination. Only the final agent executes MCP tools to prevent duplicate actions.

   MCP Server
      A service that implements the Model Context Protocol and provides tools to agents. Examples: weather service, filesystem access, web search.

   Multi-Turn Mode
      Interactive conversation mode where you can continue asking questions across multiple turns. Session history is preserved in ``.massgen/sessions/``.

   Orchestrator
      System component that manages agent coordination, voting, workspace management, and session handling.

   Planning Mode
      See :term:`MCP Planning Mode`.

   Session
      A multi-turn conversation saved in ``.massgen/sessions/``. Sessions preserve context across multiple interactions with the same agent team.

   Snapshot
      A workspace state captured during coordination. Snapshots allow agents to share file-based work with each other.

   Snapshot Storage
      Directory where workspace snapshots are stored. Configured via ``orchestrator.snapshot_storage`` in YAML.

   System Message
      Instructions or role description provided to an agent to customize its behavior. Also called "system prompt."

   Temporary Workspace
      Directory storing previous turn results for context in multi-turn sessions. Configured via ``orchestrator.agent_temporary_workspace``.

   Voting
      Process where agents evaluate solutions and cast votes for the best answer during coordination rounds.

   Voting Config
      Orchestrator settings controlling voting behavior, including consensus threshold and voting rules.

   Voting Threshold
      Minimum percentage of agent votes required to select a final answer. Configured as 0.0-1.0 (e.g., 0.6 = 60%).

   Workspace
      Isolated directory where an agent performs file operations. Each agent has its own workspace under ``.massgen/workspaces/``.

   Workspace Isolation
      Security feature ensuring each agent's file operations are contained in their own workspace, preventing accidental interference.

   YAML Configuration
      Human-readable configuration file format used to define agents, backends, and orchestrator settings in MassGen.

   .massgen Directory
      Organizational directory created by MassGen to store all working files: sessions, workspaces, snapshots, temporary files, and logs.

Deprecated Terms
================

The following terms were used in earlier versions but are no longer preferred:

.. glossary::
   :sorted:

   Working Directory
      **Deprecated**. Use :term:`Workspace` instead. The ``cwd`` parameter still refers to the workspace directory.

   Shared Directory
      **Deprecated**. Use :term:`Context Path` instead. Context paths are the current terminology for shared project directories.

   Winning Agent
      **Deprecated**. Use :term:`Final Agent` instead. This is the agent selected after coordination completes.

   Final Presentation Agent
      **Deprecated**. Use :term:`Final Agent` instead. Simpler terminology preferred.

   Provider
      **Deprecated**. Use :term:`Backend` instead. Backend is more precise as it refers to the integration code, not just the service provider.

   External Tool
      **Deprecated** when referring to MCP. Use :term:`MCP Server` or :term:`MCP (Model Context Protocol)` instead.

   MCP Tool
      **Ambiguous**. Clarify whether you mean an :term:`MCP Server` (the service) or a specific tool provided by an MCP server.

Configuration-Related Terms
============================

.. glossary::
   :sorted:

   agents
      Top-level YAML key (plural) for multi-agent configurations. Contains a list of agent definitions.

   agent
      Alternative top-level YAML key (singular) for single-agent configurations. Less commonly used.

   backend.type
      YAML parameter specifying the backend type (e.g., ``openai``, ``claude``, ``gemini``).

   backend.model
      YAML parameter specifying the model name (e.g., ``gpt-5-nano``, ``claude-sonnet-4``).

   backend.cwd
      YAML parameter specifying the agent's workspace directory.

   orchestrator.coordination
      YAML section for coordination configuration, including planning mode settings.

   orchestrator.context_paths
      YAML list of shared directories with read/write permissions.

   orchestrator.snapshot_storage
      YAML parameter for snapshot directory location.

   orchestrator.agent_temporary_workspace
      YAML parameter for temporary workspace directory location.

   permission
      YAML parameter for context path access level: ``"read"`` or ``"write"``.

Backend-Specific Terms
=======================

.. glossary::
   :sorted:

   AG2
      External framework for agentic workflows with code execution. Backend type: ``ag2``.

   Azure OpenAI
      Microsoft Azure's OpenAI deployment service. Backend type: ``azure_openai``.

   Chat Completions API
      Generic OpenAI-compatible API format. Backend type: ``chatcompletion``.

   Gemini
      Google's AI models (Flash, Pro). Backend type: ``gemini``.

   GPT
      OpenAI's language models (GPT-4, GPT-5, etc.). Backend type: ``openai``.

   Grok
      xAI's language models (Grok-3, Grok-4). Backend type: ``grok``.

   Response API
      Anthropic's API format. Backend type: ``claude``.

   SGLang
      Structured Generation Language for high-performance LLM inference. Supported via ``chatcompletion`` backend.

   vLLM
      High-performance LLM inference engine. Supported via ``chatcompletion`` backend.

   ZhipuAI / ZAI
      Chinese AI provider with GLM models. Backend type: ``zai``.

Usage Examples
==============

**Correct terminology in documentation:**

.. code-block:: rst

   The :term:`final agent` executes write operations to :term:`context paths<Context Path>`.

   Agents use :term:`MCP servers<MCP Server>` to access external tools.

   Each agent has an isolated :term:`workspace` under ``.massgen/workspaces/``.

**Preferred vs. deprecated:**

.. list-table::
   :header-rows: 1
   :widths: 40 40 20

   * - Preferred
     - Deprecated
     - Context
   * - Context path
     - Shared directory
     - Project integration
   * - Workspace
     - Working directory, cwd
     - Agent file operations
   * - Coordination phase
     - Coordination round
     - When emphasizing the phase, not iteration
   * - Final agent
     - Winning agent, final presentation agent
     - Agent selection
   * - Backend
     - Provider
     - Model integration

See Also
========

* :doc:`user_guide/concepts` - Core MassGen concepts explained
* :doc:`reference/yaml_schema` - Complete YAML parameter reference
* :doc:`quickstart/configuration` - Configuration guide with examples
* :doc:`reference/cli` - Command-line interface reference
