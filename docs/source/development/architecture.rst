Architecture
============

MassGen's architecture is designed for scalability, flexibility, and extensibility.

System Overview
---------------

.. code-block:: text

   ┌─────────────────────────────────────────┐
   │           User Application              │
   └─────────────┬───────────────────────────┘
                 │
   ┌─────────────▼───────────────────────────┐
   │          Orchestrator Layer             │
   │  ┌─────────────┬──────────────────┐    │
   │  │  Strategy   │  Consensus       │    │
   │  │  Manager    │  Engine           │    │
   │  └─────────────┴──────────────────┘    │
   └─────────────┬───────────────────────────┘
                 │
   ┌─────────────▼───────────────────────────┐
   │           Agent Layer                   │
   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
   │  │Agent1│ │Agent2│ │Agent3│ │AgentN│ │
   │  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ │
   └─────┼────────┼────────┼────────┼──────┘
         │        │        │        │
   ┌─────▼────────▼────────▼────────▼──────┐
   │         Backend Abstraction            │
   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
   │  │OpenAI│ │Claude│ │Gemini│ │ Grok │ │
   │  └──────┘ └──────┘ └──────┘ └──────┘ │
   └─────────────────────────────────────────┘

Core Components
---------------

Orchestrator
~~~~~~~~~~~~

The orchestrator manages agent coordination:

* Task distribution
* Strategy execution
* Consensus building
* Result aggregation

Agent
~~~~~

Agents are autonomous units with:

* Unique identity and role
* Backend connection
* Tool access
* Memory management

Backend
~~~~~~~

Backends provide LLM capabilities:

* API abstraction
* Model management
* Response handling
* Error recovery

Design Principles
-----------------

1. **Modularity**: Components are loosely coupled
2. **Extensibility**: Easy to add new agents, backends, tools
3. **Scalability**: Supports horizontal scaling
4. **Resilience**: Fault-tolerant design
5. **Flexibility**: Multiple orchestration strategies

Coordination Protocol
---------------------

MassGen uses a "parallel study group" coordination protocol inspired by advanced systems like xAI's Grok Heavy and Google DeepMind's Gemini Deep Think.

Vote-Based Consensus
~~~~~~~~~~~~~~~~~~~~

The coordination process follows these steps:

1. **Parallel Execution**: All agents receive the same query and work simultaneously
2. **Answer Observation**: Agents can see recent answers from other agents
3. **Decision Making**: Each agent chooses to either:

   - Provide a new/refined answer
   - Vote for an existing answer they think is best

4. **Consensus Detection**: Coordination continues until all agents have voted
5. **Winner Selection**: The agent with the most votes is selected
6. **Final Presentation**: The winning agent delivers the final answer

**Key Features:**

* **Natural Convergence**: No forced consensus, agents naturally agree on best answer
* **Iterative Refinement**: Agents can refine their answers after seeing others' work
* **Workspace Sharing**: When agents answer, their workspace is snapshotted for others to review
* **Tie Resolution**: Deterministic tie-breaking based on answer order

Answer Labeling
~~~~~~~~~~~~~~~

Each answer gets a unique identifier: ``agent{N}.{attempt}``

* ``agent1.1`` = Agent 1's first answer
* ``agent2.1`` = Agent 2's first answer
* ``agent1.2`` = Agent 1's second answer (after restart)
* ``agent1.final`` = Agent 1's final answer (if winner)

This labeling system enables:

* Clear vote tracking
* Answer evolution visualization
* Transparent decision history

Implementation: ``massgen/orchestrator.py``

Workspace Management
--------------------

Each agent gets an isolated workspace for safe file operations.

Directory Structure
~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   .massgen/
   ├── workspaces/           # Agent working directories
   │   ├── agent1/          # Agent 1's isolated workspace
   │   └── agent2/          # Agent 2's isolated workspace
   ├── snapshots/           # Workspace snapshots for coordination
   │   ├── agent1_20250113_143022/  # Snapshot of agent1's work
   │   └── agent2_20250113_143025/  # Snapshot of agent2's work
   ├── temp_workspaces/     # Previous turn results for multi-turn
   │   ├── agent1_turn_1/   # Agent 1's turn 1 results
   │   └── agent2_turn_1/   # Agent 2's turn 1 results
   ├── sessions/            # Multi-turn conversation history
   │   └── session_20250113_143000/
   │       ├── turn_1/
   │       └── turn_2/
   └── massgen_logs/        # All logging output
       └── log_20250113_143000/

Snapshot System
~~~~~~~~~~~~~~~

When an agent provides an answer during coordination:

1. **Capture**: Their workspace is copied to ``snapshots/``
2. **Share**: Other agents receive read-only access to the snapshot
3. **Review**: Agents can examine files, code, and outputs
4. **Build**: Agents build on insights from other agents' work

This enables agents to:

* See concrete work, not just descriptions
* Catch errors in code or logic
* Build incrementally on each other's contributions
* Provide informed votes based on actual outputs

Implementation: ``massgen/filesystem_manager/``

Multi-Turn Conversations
-------------------------

MassGen supports interactive multi-turn conversations with full context preservation.

Session Management
~~~~~~~~~~~~~~~~~~

Each multi-turn session maintains:

* **Session ID**: Unique identifier (e.g., ``session_20250113_143000``)
* **Turn History**: Numbered turns (``turn_1``, ``turn_2``, ...)
* **Workspace Persistence**: Each turn's workspace is preserved
* **Context Paths**: Previous turns become read-only context for next turns

Turn Lifecycle
~~~~~~~~~~~~~~

1. **Turn Start**: Increment turn counter, create turn directory
2. **Context Loading**: Previous turn's workspace becomes read-only context
3. **Execution**: Agents work with fresh writeable workspace + previous context
4. **Persistence**: Winning agent's workspace is saved to turn directory
5. **Summary Update**: SESSION_SUMMARY.txt is updated with turn details

This allows agents to:

* Compare "what I changed" vs "what was originally there"
* Build incrementally across multiple turns
* Reference previous results explicitly
* Maintain project continuity

Implementation: ``massgen/cli.py`` (multi-turn mode)

MCP Integration
---------------

MassGen integrates Model Context Protocol (MCP) for external tool access.

Architecture
~~~~~~~~~~~~

.. code-block:: text

   Backend → MCP Client → MCP Server → External Tools
      ↓
   Tools List → Agent → Tool Calls → Tool Results

Supported Backends:

* **Claude**: Native MCP support via ``claude_messages`` API
* **Gemini**: MCP support via function calling
* **Others**: Via tool conversion layer

Planning Mode
~~~~~~~~~~~~~

Special coordination mode for MCP tools:

* **During Coordination**: Agents can *plan* tool usage without execution
* **After Consensus**: Winner executes tools in their final answer
* **Safety**: Prevents irreversible actions during collaboration

This is critical for:

* File operations (create, delete, modify)
* API calls with side effects
* Database operations
* External service integrations

Implementation: ``massgen/backend/gemini.py``, ``massgen/backend/claude.py``

Backend Abstraction
-------------------

All LLM interactions go through a unified backend interface.

Backend Interface
~~~~~~~~~~~~~~~~~

Each backend implements:

.. code-block:: python

   class Backend:
       async def chat(messages, stream=True):
           """Stream responses with tool calls"""

       async def get_available_tools():
           """Return tools for this backend"""

       def format_messages(messages):
           """Convert to backend-specific format"""

Supported Backends:

* **API-based**: OpenAI, Claude, Gemini, Grok, Azure OpenAI
* **Local**: LM Studio, vLLM, SGLang
* **External**: AG2 framework agents
* **Custom**: Claude Code CLI with filesystem access

Implementation: ``massgen/backend/``

File Permission System
----------------------

MassGen enforces granular file permissions for safe project integration.

Context Paths
~~~~~~~~~~~~~

Agents can access specific directories with permissions:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/path/to/project"
         permission: "write"
         protected_paths:
           - ".git"
           - "node_modules"

Permission Types:

* ``read``: View files only
* ``write``: Read, create, modify, delete files (except protected)

Protected Paths:

* Immune from modification/deletion
* Relative to context path
* Supports files and directories

Safety Features:

* **Read-Before-Delete**: Agents must read files before deletion
* **Permission Validation**: All file operations are checked
* **Audit Trail**: All operations logged to massgen.log

Implementation: ``massgen/filesystem_manager/_path_permission_manager.py``

Code Organization
-----------------

.. code-block:: text

   massgen/
   ├── orchestrator.py           # Coordination engine
   ├── chat_agent.py             # Agent implementations
   ├── cli.py                    # Command-line interface
   ├── config_builder.py         # Interactive config wizard
   ├── agent_config.py           # Configuration models
   ├── backend/                  # LLM backend implementations
   │   ├── claude.py            # Anthropic Claude
   │   ├── gemini.py            # Google Gemini
   │   ├── response.py          # OpenAI
   │   ├── grok.py              # xAI Grok
   │   ├── claude_code.py       # Claude Code CLI
   │   ├── external.py          # External frameworks (AG2)
   │   └── ...
   ├── frontend/                 # UI components
   │   └── coordination_ui.py   # Terminal UI
   ├── filesystem_manager/       # File operations & permissions
   │   ├── _path_permission_manager.py
   │   ├── _workspace_tools_server.py
   │   └── ...
   ├── logger_config.py          # Logging configuration
   └── adapters/                 # External framework adapters
       └── ag2/                 # AG2 adapter

Key Modules:

* **orchestrator.py**: Vote tracking, consensus detection, workspace snapshots
* **chat_agent.py**: Agent lifecycle, message handling, tool execution
* **backend/**: LLM-specific implementations with unified interface
* **filesystem_manager/**: Permission system, workspace isolation
* **frontend/**: Real-time coordination display with Rich

Extension Points
----------------

Adding New Backends
~~~~~~~~~~~~~~~~~~~

1. Subclass ``Backend`` base class
2. Implement ``chat()`` and ``format_messages()``
3. Register in ``cli.py``'s ``create_backend()``
4. Add to ``AgentConfig`` factory methods

Example: ``massgen/backend/grok.py``

Adding MCP Servers
~~~~~~~~~~~~~~~~~~

1. Configure in YAML:

   .. code-block:: yaml

      backend:
        type: "claude"
        mcp_servers:
          - name: "weather"
            command: "npx"
            args: ["-y", "@modelcontextprotocol/server-weather"]

2. Servers auto-start when backend initializes
3. Tools automatically discovered and presented to agent

Example: All MCP configs in ``massgen/configs/tools/mcp/``

Adding External Frameworks
~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Create adapter in ``massgen/adapters/{framework}/``
2. Implement ``ExternalAgentAdapter`` interface
3. Register in ``adapters/__init__.py``
4. Agents work seamlessly with native MassGen agents

Example: ``massgen/adapters/ag2/``

Performance Considerations
--------------------------

* **Parallel Execution**: All agents run concurrently
* **Streaming**: All responses stream in real-time
* **Workspace Isolation**: Copy-on-write for efficiency
* **Async I/O**: All file operations are non-blocking
* **Token Management**: Per-backend rate limiting

See Also
--------

* :doc:`contributing` - How to contribute code
* :doc:`writing_configs` - Configuration authoring guide
* ``massgen/orchestrator.py`` - Core coordination logic
* ``massgen/backend/`` - Backend implementations
* ``massgen/filesystem_manager/`` - Permission system