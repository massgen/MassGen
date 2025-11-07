Interactive Multi-Turn Mode
===========================

MassGen supports interactive mode where you can have ongoing conversations with the system. Agents maintain context across multiple turns and collaborate on each response.

Starting Interactive Mode
--------------------------

Simply omit the question when running MassGen to enter interactive chat mode:

**Single agent:**

.. code-block:: bash

   # Interactive mode with quick model selection
   massgen --model gpt-5-mini

**Multi-agent:**

.. code-block:: bash

   # Multi-agent interactive mode
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml

**The Interactive Interface:**

.. code-block:: text

   ╭──────────────────────────────────────────────────────────────────────────────╮
   │                                                                              │
   │       ███╗   ███╗ █████╗ ███████╗███████╗ ██████╗ ███████╗███╗   ██╗         │
   │       ████╗ ████║██╔══██╗██╔════╝██╔════╝██╔════╝ ██╔════╝████╗  ██║         │
   │       ██╔████╔██║███████║███████╗███████╗██║  ███╗█████╗  ██╔██╗ ██║         │
   │       ██║╚██╔╝██║██╔══██║╚════██║╚════██║██║   ██║██╔══╝  ██║╚██╗██║         │
   │       ██║ ╚═╝ ██║██║  ██║███████║███████║╚██████╔╝███████╗██║ ╚████║         │
   │       ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝         │
   │                                                                              │
   │            🤖 🤖 🤖  →  💬 collaborate  →  🎯 winner  →  📢 final            │
   │                                                                              │
   ╰──────────────────────────────────────────────────────────────────────────────╯

   ╭──────────────────────────────────────────────────────────────────────────────╮
   │    🤝 Mode:                Multi-Agent (3 agents)                            │
   │      ├─ openai_agent_1:    gpt-5 (Response)                                  │
   │      ├─ gemini_agent_2:    gemini-2.5-flash (Gemini)                         │
   │      └─ grok_agent_3:      grok-4-fast-reasoning (Grok)                      │
   ╰──────────────────────────────────────────────────────────────────────────────╯

   ╭──────────────────────────────────────────────────────────────────────────────╮
   │  💬  Type your questions below                                               │
   │  💡  Use slash commands: /help, /quit, /reset, /status, /config              │
   │  ⌨️   Press Ctrl+C to exit                                                   │
   ╰──────────────────────────────────────────────────────────────────────────────╯

How It Works
------------

In interactive mode:

1. **Context Preservation** - Each response builds on previous conversation history
2. **Multi-Agent Collaboration** - Agents continue to vote and reach consensus on each turn
3. **Session Management** - All conversation state preserved in ``.massgen/sessions/``
4. **Natural Conversation** - Type your questions, press Enter, get collaborative responses

**Example session:**

.. code-block:: text

   You: What is machine learning?
   [Agents collaborate and provide comprehensive answer]

   You: Give me a practical example of supervised learning
   [Agents use context from previous turn to provide relevant examples]

   You: How can I implement that in Python?
   [Agents build on previous examples with implementation code]

   You: /quit
   Exiting MassGen. Goodbye!

Interactive Features
--------------------

Multi-Turn Conversations
~~~~~~~~~~~~~~~~~~~~~~~~

Multiple agents collaborate to chat with you in an ongoing conversation. Each agent:

* Sees full conversation history
* Builds on previous responses
* Votes and reaches consensus on each turn
* Maintains context about your goals and preferences

Real-Time Coordination Tracking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Live visualization of agent interactions:

* Agent coordination table showing votes and consensus
* Real-time phase transitions (Initial → Coordination → Presentation)
* Voting progress and decision-making processes
* Streaming agent responses

Interactive Coordination Table
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Press ``r`` during a session to view:

* Complete history of agent coordination events
* State transitions for each agent
* Voting patterns and consensus evolution
* Timeline of the conversation

Session Management
------------------

Session Storage
~~~~~~~~~~~~~~~

When using interactive mode, MassGen automatically stores session state in:

.. code-block:: text

   .massgen/
   └── sessions/
       └── session_20250108_143022/
           ├── turn_1/               # Results from first turn
           │   ├── agent_outputs/
           │   └── coordination_log.json
           ├── turn_2/               # Results from second turn
           │   ├── agent_outputs/
           │   └── coordination_log.json
           └── SESSION_SUMMARY.txt   # Human-readable summary

Benefits:

* **Resume sessions** - Continue from where you left off
* **Review history** - Examine past turns and agent decisions
* **Debug conversations** - Understand coordination patterns
* **Track progress** - See how agents evolved their understanding

Configuration
~~~~~~~~~~~~~

Interactive mode uses the same YAML configuration as single-turn mode:

.. code-block:: yaml

   agents:
     - id: "agent1"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
     - id: "agent2"
       backend:
         type: "openai"
         model: "gpt-5-nano"

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

Working with Project Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Multi-turn mode supports full filesystem integration for working with your codebase across multiple turns:

.. code-block:: yaml

   orchestrator:
     # Share read-only source code across all agents
     context_paths:
       - path: "src/"
         permission: "read"
       - path: "tests/"
         permission: "read"
       - path: "docs/"
         permission: "read"

     # Agent workspaces for file modifications
     agent_temporary_workspace: ".massgen/temp_workspaces"
     snapshot_storage: ".massgen/snapshots"

   agents:
     - id: "agent_a"
       backend:
         type: "claude"
         model: "claude-sonnet-4"

         # Agent-specific workspace for modifications
         cwd: "workspace_a"
         # File operations handled automatically via cwd parameter

**Key Features:**

* **``context_paths``** - Grant agents read-only access to your source code
* **``cwd``** - Each agent gets isolated workspace for file modifications
* **``agent_temporary_workspace``** - Temporary workspaces preserved across turns
* **``snapshot_storage``** - Workspace snapshots saved between turns

**Example workflow:**

.. code-block:: text

   You: Read the authentication module and explain how it works
   [Agents access src/ via context_paths and analyze code]

   You: Create an improved version with better error handling
   [Agents write to their workspace_a/ with modifications]

   You: Add unit tests for the new error handling
   [Agents build on previous turn's work, maintaining full context]

Interactive Commands
--------------------

Special commands available during interactive sessions:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Command
     - Description
   * - ``/help`` or ``/h``
     - Show available commands and help message
   * - ``/status``
     - Show current session status (agents, mode, conversation history, config path)
   * - ``/config``
     - Open configuration file in default editor (macOS, Windows, Linux)
   * - ``/clear`` or ``/reset``
     - Reset conversation history and start fresh
   * - ``/quit`` or ``/exit`` or ``/q``
     - Exit interactive mode
   * - ``Ctrl+C``
     - Exit interactive mode
   * - ``r`` (during execution)
     - View complete coordination history

Real-Time Feedback
------------------

The system displays real-time agent and system status:

**Phase Indicators:**

.. code-block:: text

   ┌─ Initial Answer Generation ────────────────┐
   │ Agent1: Generating...                      │
   │ Agent2: Generating...                      │
   │ Agent3: Complete ✓                         │
   └────────────────────────────────────────────┘

**Coordination Table:**

.. code-block:: text

   ┌─ Coordination Round 1 ─────────────────────┐
   │ Agent     │ Status      │ Votes            │
   ├───────────┼─────────────┼──────────────────┤
   │ Agent1    │ Voted       │ Agent3           │
   │ Agent2    │ Voting...   │ -                │
   │ Agent3    │ Converged   │ Self             │
   └────────────────────────────────────────────┘

**Streaming Output:**

Watch agents' reasoning and responses develop in real-time as they think through the problem.

Use Cases for Interactive Mode
-------------------------------

**Iterative Research**
   Explore topics progressively, diving deeper based on previous responses.

**Code Development**
   Build projects step-by-step with agents refining code based on feedback.

**Learning and Tutoring**
   Ask follow-up questions to clarify concepts and build understanding.

**Exploratory Analysis**
   Investigate datasets or documents with agents maintaining analysis context.

**Creative Writing**
   Develop stories or content iteratively with collaborative refinement.

Example: Iterative Code Development
------------------------------------

.. code-block:: bash

   # Start interactive session with file operations
   massgen \
     --config @examples/tools/filesystem/claude_code_single.yaml

Session example:

.. code-block:: text

   You: Create a simple Flask web app
   [Agents create basic Flask structure]

   You: Add user authentication
   [Agents add authentication using context of existing structure]

   You: Add a database for storing user preferences
   [Agents integrate database with existing auth system]

   You: Write tests for the authentication
   [Agents create tests covering the implemented features]

Each turn builds on the work from previous turns, with agents maintaining full context of the evolving project.

Debugging Interactive Sessions
-------------------------------

Enable debug mode for detailed logging:

.. code-block:: bash

   massgen \
     --debug \
     --config @examples/basic/multi/three_agents_default.yaml

Debug logs saved to ``agent_outputs/log_{timestamp}/massgen_debug.log`` include:

* Full conversation history
* Agent decision-making processes
* Coordination events and state transitions
* Tool calls and backend operations

Best Practices
--------------

1. **Start Broad** - Begin with general questions, then drill down
2. **Reference Previous Turns** - Use "that", "the previous", "your earlier suggestion"
3. **Clear When Switching Topics** - Use ``/clear`` to reset context
4. **Review Coordination** - Press ``r`` to understand agent decision patterns
5. **Save Important Outputs** - Session storage preserves all turns for later review

Next Steps
----------

* :doc:`file_operations` - Learn about file operations in multi-turn sessions
* :doc:`project_integration` - Work with your codebase across multiple turns
* :doc:`mcp_integration` - Use MCP tools in interactive mode
* :doc:`../quickstart/running-massgen` - More CLI examples
