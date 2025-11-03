Memory and Context Management
==============================

MassGen's memory system enables agents to maintain knowledge across conversations, handle long context windows gracefully, and share insights across multi-turn sessions. The system automatically manages context compression, semantic memory retrieval, and cross-agent knowledge sharing.

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
--------

The memory system consists of two complementary components:

**ConversationMemory (Short-term)**
   Fast in-memory storage for recent messages. Maintains verbatim conversation history for the current context window.

**PersistentMemory (Long-term)**
   Vector database storage (via `mem0 <https://mem0.ai>`_) with semantic search. Extracts and stores key facts that persist across sessions and can be retrieved when relevant.

Key Features
~~~~~~~~~~~~

- **Automatic Context Compression**: When approaching token limits, old messages are removed while remaining accessible via semantic search
- **Semantic Retrieval**: Retrieve relevant facts from past conversations based on current context
- **Cross-Agent Memory Sharing**: Agents access previous winning agents' knowledge from past turns
- **Session Management**: Memories isolated by session for clean separation of different tasks
- **Turn-Aware Filtering**: Prevents temporal leakage by filtering memories by turn number

Quick Start
-----------

Prerequisites
~~~~~~~~~~~~~

For multi-agent setups, start the Qdrant vector database server:

.. code-block:: bash

   # Start Qdrant (required for persistent memory)
   docker-compose -f docker-compose.qdrant.yml up -d

   # Verify it's running
   curl http://localhost:6333/health

   # (Optional) View Qdrant dashboard
   open http://localhost:6333/dashboard

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Add memory configuration to your YAML config:

.. code-block:: yaml

   memory:
     enabled: true

     conversation_memory:
       enabled: true  # Short-term tracking

     persistent_memory:
       enabled: true  # Long-term storage

       # LLM for fact extraction (uses mem0's native providers)
       llm:
         provider: "openai"
         model: "gpt-4.1-nano-2025-04-14"

       # Embeddings for vector search
       embedding:
         provider: "openai"
         model: "text-embedding-3-small"

       # Qdrant configuration
       qdrant:
         mode: "server"  # Use "local" for single-agent only
         host: "localhost"
         port: 6333

     # Context compression settings
     compression:
       trigger_threshold: 0.75  # Compress at 75% usage
       target_ratio: 0.40       # Keep 40% after compression

     # Retrieval settings
     retrieval:
       limit: 5              # Facts to retrieve
       exclude_recent: true  # Only retrieve after compression

Run with Memory
~~~~~~~~~~~~~~~

.. code-block:: bash

   # Interactive mode with memory
   massgen --config @examples/memory/gpt5mini_gemini_context_window_management.yaml

   # Single question with memory
   massgen \
     --config @examples/memory/gpt5mini_gemini_context_window_management.yaml \
     "Analyze the MassGen codebase and create an architecture document"

How It Works
------------

Custom Fact Extraction
~~~~~~~~~~~~~~~~~~~~~~~

MassGen uses custom prompts designed to extract high-quality, domain-focused memories. The goal is to filter facts to be:

**Self-Contained and Specific**:
   Facts should be understandable 6 months later without the original conversation

**Focused on Domain Knowledge**:
   - ✅ Concrete data points with context ("OpenAI revenue reached $12B annualized")
   - ✅ Insights with explanations ("Narrative depth valued in creative writing because...")
   - ✅ Capabilities with use cases ("MassGen v0.1.1 supports Python tools via YAML")
   - ✅ Domain expertise with details ("Binet's formula uses golden ratio phi=(1+√5)/2")
   - ✅ Specific recommendations with WHAT, WHEN, WHY

**Intended to Exclude System Internals** (to improve in future):
   - ❌ Agent comparisons ("Agent 1's response is better")
   - ❌ Voting details ("The reason for voting...")
   - ❌ File paths and line numbers (become outdated)
   - ❌ Meta-instructions ("Response should start with...")
   - ❌ Generic advice ("Providing templates improves docs")

**Implementation**: ``massgen/memory/_fact_extraction_prompts.py::MASSGEN_UNIVERSAL_FACT_EXTRACTION_PROMPT``

Memory Flow
~~~~~~~~~~~

**Every Turn**:

1. User message added to conversation_memory (verbatim)
2. Agent responds with reasoning and answer
3. Response recorded to:

   - **ConversationMemory**: Full message for immediate context
   - **PersistentMemory**: mem0's LLM extracts key facts and stores in vector DB

4. Context window checked:

   - **Below threshold**: Continue normally
   - **Above threshold**: Compress old messages, enable retrieval

**What Gets Recorded**:

.. code-block:: text

   ✅ User messages
   ✅ Agent reasoning (full reasoning chains)
   ✅ Reasoning summaries
   ✅ Final answer text

   ❌ System messages (orchestrator prompts - filtered out)
   ❌ Workflow tools (vote/new_answer - internal coordination)
   ❌ MCP tool calls (read_file, list_directory - implementation details)

**Why these filters?** See :ref:`design-decisions` below.

Context Compression
~~~~~~~~~~~~~~~~~~~

When context usage exceeds the threshold (default 75%):

1. **Select messages to keep**: System messages + recent messages fitting in target ratio (default 40%)
2. **Remove old messages** from conversation_memory (already in persistent_memory)
3. **Enable retrieval** for subsequent turns

.. code-block:: text

   Before Compression:
   📊 Context: 96,000 / 128,000 tokens (75%)
   [user msg 1] → [agent response 1] → ... → [user msg 20] → [agent response 20]

   After Compression:
   📊 Context: 51,200 / 128,000 tokens (40%)
   [user msg 15] → [agent response 15] → ... → [user msg 20] → [agent response 20]

   Old messages (1-14) → Accessible via semantic search in persistent_memory

Memory Retrieval
~~~~~~~~~~~~~~~~

Retrieval happens when:

- ✅ **After compression**: Retrieve facts from compressed messages
- ✅ **On restart/reset**: Restore recent context
- ❌ **Before compression**: Skip (all context already in conversation_memory)

Retrieval process:

1. **Search own agent's memories** (all turns, current session)
2. **Search previous winners' memories** (filtered by turn - see below)
3. **Format and inject** as system message before processing

.. code-block:: text

   Retrieved memories injected as:

   ┌─────────────────────────────────────┐
   │ Relevant memories:                   │
   │ • User asked about backend system    │
   │ • Agent analyzed 5 backend files     │
   │ • [From agent_b Turn 1] Explained    │
   │   stateful vs stateless backends     │
   └─────────────────────────────────────┘
   ↓
   [user msg 15] → [agent response 15] → ...

Use Cases
---------

Scenario 1: Long Analysis Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Use case**: Analyzing a large codebase that requires reading 50+ files

**Without memory**:
   Context fills up after ~15 files, agent loses track of earlier analysis

**With memory**:
   - Agent reads files 1-15, context compresses
   - Files 16-30: Agent retrieves relevant facts from 1-15
   - Maintains complete understanding throughout analysis

**Configuration**:

.. code-block:: yaml

   memory:
     enabled: true
     compression:
       trigger_threshold: 0.75  # Compress when 75% full
       target_ratio: 0.40        # Keep 40% of recent context

**Example**:

.. code-block:: bash

   massgen --config @examples/memory/gpt5mini_gemini_context_window_management.yaml \
     "Analyze the entire MassGen codebase and create comprehensive documentation"

Scenario 2: Multi-Turn Sessions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Use case**: Interactive development across multiple sessions

**Without memory**:
   Each turn starts fresh, agents forget previous turns' insights

**With memory**:
   - Turn 1: Agent A wins, explains backend architecture
   - Turn 2: Agent B retrieves Agent A's Turn 1 insights
   - Turn 3: Agent A sees both own past work + Agent B's Turn 2 insights

**How winner memory sharing works**:

.. code-block:: text

   Turn 1: agent_a wins → Memories tagged {"agent_id": "agent_a", "turn": 1}
   Turn 2:
     agent_b retrieves:
       ✅ Own memories (all turns)
       ✅ agent_a's Turn 1 memories (previous winner)
       ❌ agent_a's Turn 2 memories (not yet complete)

   Turn 3:
     agent_a retrieves:
       ✅ Own memories (Turns 1, 2)
       ✅ agent_b's Turn 2 memories (previous winner)

**Configuration**:

Session ID automatically generated for interactive mode: ``session_20251028_143000``

Memories are isolated per session unless you specify a custom session name.

Scenario 3: Orchestrator Restarts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Use case**: Agent needs to restart due to errors or new answers from other agents

**Without memory**:
   Partial work lost, agent starts from scratch

**With memory**:
   - Before restart: Current conversation recorded to persistent_memory
   - On restart: Relevant facts retrieved to restore context
   - Agent continues seamlessly with knowledge of prior attempts

**Example flow**:

.. code-block:: text

   Agent A working on task...
   📝 Read 5 files, analyzed architecture
   🔄 Other agent submits better answer → Restart triggered
   💾 Recording 10 messages before reset
   🔄 Retrieving memories after reset...
   💭 Retrieved: "Analyzed backend/base.py", "Found adapter pattern", ...
   ✅ Agent continues with restored context

Configuration Reference
-----------------------

Complete Configuration
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   memory:
     # Global enable/disable
     enabled: true

     # Short-term conversation tracking
     conversation_memory:
       enabled: true

     # Long-term knowledge storage
     persistent_memory:
       enabled: true
       on_disk: true  # Persist across restarts

       # Session isolation (optional)
       # session_name: "my_project_analysis"  # Specific session
       # session_name: null                   # Cross-session memory

       # LLM for fact extraction
       llm:
         provider: "openai"
         model: "gpt-4.1-nano-2025-04-14"  # Fast, cheap for memory ops
         # api_key: "sk-..."  # Optional - reads from OPENAI_API_KEY env var

       # Embeddings for vector search
       embedding:
         provider: "openai"
         model: "text-embedding-3-small"
         # api_key: "sk-..."  # Optional - reads from OPENAI_API_KEY env var

       # Vector store (Qdrant)
       qdrant:
         mode: "server"      # "server" or "local"
         host: "localhost"   # Server mode only
         port: 6333          # Server mode only
         # path: ".massgen/qdrant"  # Local mode only

     # Context window compression
     compression:
       trigger_threshold: 0.75  # Compress at 75% context usage
       target_ratio: 0.40       # Target 40% after compression

     # Memory retrieval
     retrieval:
       limit: 5              # Max facts per agent
       exclude_recent: true  # Skip retrieval before compression

Configuration Options
~~~~~~~~~~~~~~~~~~~~~

Memory Toggle
^^^^^^^^^^^^^

.. code-block:: yaml

   memory:
     enabled: false  # Disable entire memory system

Conversation Memory
^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   conversation_memory:
     enabled: true  # Almost always true - needed for context management

Persistent Memory
^^^^^^^^^^^^^^^^^

**LLM Configuration** (for fact extraction):

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Provider
     - Configuration
   * - OpenAI
     - ``provider: "openai"``, ``model: "gpt-4.1-nano-2025-04-14"`` or ``"gpt-4o-mini"``
   * - Anthropic
     - ``provider: "anthropic"``, ``model: "claude-3-5-haiku-20241022"``
   * - Groq
     - ``provider: "groq"``, ``model: "llama-3.1-8b-instant"``

**Embedding Configuration** (for vector search):

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Provider
     - Configuration
   * - OpenAI
     - ``provider: "openai"``, ``model: "text-embedding-3-small"`` (1536 dims)
   * - Together
     - ``provider: "together"``, ``model: "togethercomputer/m2-bert-80M-8k-retrieval"``
   * - Azure OpenAI
     - ``provider: "azure_openai"``, ``model: "text-embedding-ada-002"``

**Qdrant Configuration**:

.. code-block:: yaml

   # Server mode (RECOMMENDED for multi-agent)
   qdrant:
     mode: "server"
     host: "localhost"
     port: 6333

   # Local mode (single agent only)
   qdrant:
     mode: "local"
     path: ".massgen/qdrant"

.. warning::
   Local file-based Qdrant does NOT support concurrent access. For multi-agent setups, always use server mode.

Session Management
^^^^^^^^^^^^^^^^^^

**Automatic sessions**:

- **Interactive mode**: ``session_20251028_143000`` (shared across all turns)
- **Single question**: ``temp_20251028_143000`` (isolated per run)

**Custom sessions**:

.. code-block:: yaml

   persistent_memory:
     session_name: "my_project_analysis"  # Continue specific session

**Cross-session memory** (search across all sessions):

.. code-block:: yaml

   persistent_memory:
     session_name: null  # or omit the field

Compression Settings
^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   compression:
     trigger_threshold: 0.75  # Compress when 75% full
     target_ratio: 0.40        # Keep 40% after compression

Example configurations:

- **Aggressive compression**: ``trigger_threshold: 0.50``, ``target_ratio: 0.20``
- **Conservative**: ``trigger_threshold: 0.90``, ``target_ratio: 0.60``

Retrieval Settings
^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   retrieval:
     limit: 5              # Max facts per agent (default: 5)
     exclude_recent: true  # Smart retrieval (default: true)

- **More context**: Increase ``limit`` to 10-20 (uses more tokens)
- **Always retrieve**: Set ``exclude_recent: false`` (may duplicate recent context)

Monitoring and Debugging
-------------------------

Context Window Logs
~~~~~~~~~~~~~~~~~~~

Monitor context usage in real-time:

.. code-block:: text

   📊 Context Window (Turn 5): 45,000 / 128,000 tokens (35%)

When compression triggers:

.. code-block:: text

   ⚠️  Context Window (Turn 11): 96,000 / 128,000 tokens (75%) - Approaching limit!
   🔄 Attempting compression (96,000 → 51,200 tokens)
   📦 Context compressed: Removed 15 messages (44,800 tokens).
      Kept 8 recent messages (51,200 tokens).

Memory Operations
~~~~~~~~~~~~~~~~~

**Recording**:

.. code-block:: text

   🔍 [_mem0_add] Recording to mem0 (agent=agent_a, session=session_123, turn=1)
      messages: 2 message(s)
      assistant: [Reasoning] I analyzed the backend files...
      assistant: The backend system consists of...
   ✅ mem0 extracted 5 fact(s), 2 relation(s)

**Retrieval**:

.. code-block:: text

   🔄 Retrieving memories after reset for agent_a (restoring recent context + 1 winner(s))...
   🔍 [retrieve] Searching memories (agent=agent_a, limit=5, winners=1)
      Previous winners: [{'agent_id': 'agent_b', 'turn': 1}]
      🔎 Searching own memories (agent_a)...
         → Found 3 memory/memories
      🔎 Searching 1 previous winner(s)...
         → Searching agent_b (turn 1)...
            Found 2 memory/memories
   ✅ Total: 5 memories retrieved
      [1] User asked about MassGen architecture
      [2] [From agent_b Turn 1] Explained the adapter pattern

Debug Files
~~~~~~~~~~~

Full message dumps saved to:

.. code-block:: text

   .massgen/massgen_logs/log_{timestamp}/turn_{N}/attempt_{M}/memory_debug/
   ├── mem0_add_agent_a_143022_123456.json  # What was recorded
   ├── mem0_add_agent_b_143025_789012.json
   └── ...

Each file contains:

.. code-block:: json

   {
     "timestamp": "143022_123456",
     "agent_id": "agent_a",
     "session_id": "session_20251028_143000",
     "metadata": {"turn": 1},
     "messages": [
       {
         "role": "assistant",
         "content": "[Reasoning]\nI need to analyze..."
       },
       {
         "role": "assistant",
         "content": "The backend system uses..."
       }
     ]
   }

Testing Memory Setup
~~~~~~~~~~~~~~~~~~~~

Verify your memory configuration:

.. code-block:: bash

   # Run test script
   uv run python scripts/test_memory_setup.py

Expected output:

.. code-block:: text

   🧪 MEMORY SYSTEM TEST SUITE

   ============================================================
   TEST 1: Environment Variables
   ============================================================
   ✅ OPENAI_API_KEY found (starts with: sk-proj...)

   ============================================================
   TEST 2: OpenAI Embedding API
   ============================================================
   ✅ Embedding successful!
      Vector dimensions: 1536

   ============================================================
   TEST 3: mem0 LLM API (gpt-4.1-nano)
   ============================================================
   ✅ LLM call successful!

   ============================================================
   TEST 4: Qdrant Connection
   ============================================================
   ✅ Qdrant server connected!

   ============================================================
   TEST 5: Full Memory Integration
   ============================================================
   ✅ PersistentMemory created!
   ✅ Messages recorded!

Advanced Usage
--------------

Per-Agent Memory Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Override memory settings for specific agents:

.. code-block:: yaml

   memory:
     # Global defaults
     retrieval:
       limit: 5

   agents:
     - id: "researcher"
       memory:
         retrieval:
           limit: 20  # This agent gets more context

     - id: "writer"
       memory:
         retrieval:
           limit: 3   # This agent gets less

Different Embedding Providers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Using Together AI** (cost-effective):

.. code-block:: yaml

   persistent_memory:
     embedding:
       provider: "together"
       model: "togethercomputer/m2-bert-80M-8k-retrieval"
       # Reads TOGETHER_API_KEY from environment

**Using Azure OpenAI**:

.. code-block:: yaml

   persistent_memory:
     llm:
       provider: "azure_openai"
       model: "gpt-4o-mini"
       api_key: "${AZURE_OPENAI_API_KEY}"
     embedding:
       provider: "azure_openai"
       model: "text-embedding-ada-002"

Session Continuation
~~~~~~~~~~~~~~~~~~~~

**Continue a previous session**:

.. code-block:: yaml

   persistent_memory:
     session_name: "codebase_analysis_oct2025"

All agents will access memories from this session across multiple CLI runs.

**Cross-session knowledge**:

.. code-block:: yaml

   persistent_memory:
     session_name: null  # Search across ALL sessions

Useful for:
- Building knowledge base across projects
- Learning from past conversations
- Avoiding repeating analysis

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

**Qdrant Connection Error**

.. code-block:: text

   ⚠️  Failed to create shared Qdrant client: Storage folder .massgen/qdrant
   is already accessed by another instance

**Solution**:

1. Check if Qdrant server is running:

   .. code-block:: bash

      docker-compose -f docker-compose.qdrant.yml ps

2. Remove stale lock files:

   .. code-block:: bash

      ./scripts/cleanup_qdrant_lock.sh
      # Or manually:
      rm .massgen/qdrant/.lock

3. Use server mode for multi-agent:

   .. code-block:: yaml

      qdrant:
        mode: "server"

**API Key Not Found**

.. code-block:: text

   ⚠️  OPENAI_API_KEY not found in environment - embedding will fail!

**Solution**:

Create ``.env`` file in project root:

.. code-block:: bash

   OPENAI_API_KEY=sk-proj-...
   ANTHROPIC_API_KEY=sk-ant-...  # If using Anthropic

**No Memories Retrieved**

.. code-block:: text

   🔄 Retrieving memories after reset...
   ℹ️  No relevant memories found

**This is normal if**:
- First turn (no memories yet)
- Query doesn't match stored memories semantically
- mem0 hasn't processed messages yet (async extraction)

**Check**:
1. Verify recording succeeded: Look for ``✅ mem0 extracted X fact(s)`` in logs
2. Browse Qdrant collections: http://localhost:6333/dashboard
3. Check debug files: ``.massgen/.../memory_debug/*.json``

Cleaning Up
~~~~~~~~~~~

**Stop Qdrant**:

.. code-block:: bash

   docker-compose -f docker-compose.qdrant.yml down

**Clear all memories**:

.. code-block:: bash

   # Remove Qdrant storage (WARNING: deletes all memories!)
   rm -rf .massgen/qdrant_storage

**Clear session data**:

.. code-block:: bash

   # Remove specific session
   rm -rf .massgen/memory_test_sessions/session_20251028_143000

   # Or all sessions
   rm -rf .massgen/memory_test_sessions

.. _design-decisions:

Design Decisions
----------------

.. raw:: html

   <details>
   <summary><strong>Why These Architecture Choices?</strong> (Click to expand)</summary>

Why mem0's Native LLMs/Embedders?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision**: Use mem0's built-in providers (OpenAI, Anthropic, etc.) instead of wrapping MassGen backends

**Rationale**:

- **Simpler**: No adapter layer, direct integration
- **No async issues**: mem0's adapters are sync, wrapping async MassGen backends caused event loop conflicts
- **Optimized**: mem0's default (gpt-4.1-nano) is optimized for memory operations
- **Flexible**: Support for many providers without custom code

**Trade-off**: Requires separate API keys (can't reuse agent's backend). But memory operations are cheap (~1-2 cents/session).

Why Skip MCP Tool Calls in Memory?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision**: Don't record MCP tool executions (read_file, list_directory, etc.)

**Rationale**:

1. **Implementation details**: HOW the work was done, not WHAT was learned
2. **Redundant**: The final answer already captures insights from reading those files
3. **Noise**: 50+ file reads create clutter, make it harder for mem0 to extract semantic facts
4. **Focus on decisions**: Agent's reasoning ("I analyzed the backend") is more valuable than execution trace

**Example**:

- ❌ Don't record: ``[Tool: read_file] path=/foo/bar.py``
- ✅ Do record: ``[Reasoning] I analyzed bar.py and found the adapter pattern``
- ✅ Final answer contains: "The backend uses an adapter pattern located in bar.py"

**If you need execution history**: Check orchestrator logs or agent context files, not memory.

Why Record Reasoning?
~~~~~~~~~~~~~~~~~~~~~

**Decision**: Include full reasoning chains and summaries in memory

**Rationale**:

- **Context for decisions**: Final answer is meaningless without the reasoning
- **Better fact extraction**: mem0's LLM can extract richer facts from reasoning
- **Debugging**: Understand WHY agent made certain choices
- **Learning**: Future turns benefit from understanding past reasoning

**Example memory facts extracted**:

- Without reasoning: "Agent said backend uses adapters"
- With reasoning: "Agent analyzed base.py first, then compared 5 implementations, concluded adapters enable provider abstraction"

Why Filter System Messages?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision**: Exclude ``role: "system"`` messages from memory

**Rationale**:

- **Orchestrator noise**: System messages contain coordination prompts like "You are evaluating answers from multiple agents..."
- **Not conversation content**: System prompts are framework instructions, not user/agent dialogue
- **Bloat**: Can be 5-10KB per message, mostly boilerplate
- **Focus on semantics**: User questions and agent answers are what matter for memory

Why Smart Retrieval (exclude_recent)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision**: Default ``exclude_recent: true`` - only retrieve after compression

**Rationale**:

- **Before compression**: All context already in conversation_memory sent to LLM
- **Retrieval would duplicate**: Waste tokens on information already present
- **After compression**: Old messages removed, retrieval fills the gap
- **On restart**: Always retrieve to restore context

**Token efficiency**:

- Without exclude_recent: ~500 extra tokens per turn (duplicated context)
- With exclude_recent: ~100 tokens only when needed (after compression)

Context Compression Thresholds
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision**: Default 75% trigger, 40% target

**Rationale**:

- **75% trigger**: Provides buffer before hitting limit (avoid truncation)
- **40% target**: Balances context retention vs. token budget
- **Room for retrieval**: Retrieved facts + recent context fit comfortably
- **Headroom for response**: LLM has space to generate long responses

**Alternative configurations**:

- **Long analysis tasks**: Lower threshold (50%) to compress more aggressively
- **Short conversations**: Higher threshold (90%) to compress rarely

Why Qdrant Server for Multi-Agent?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision**: Require Qdrant server mode (Docker) for multi-agent setups

**Rationale**:

- **Concurrent access**: File-based Qdrant locks on first access
- **Performance**: Server mode handles parallel searches better
- **Robustness**: No stale lock files from crashed processes
- **Scalability**: Can scale to many agents

**Trade-off**: Requires Docker. But setup is one command: ``docker-compose up -d``

Why Separate Memories Per Agent?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision**: Each agent has isolated memories, filtered by ``agent_id``

**Rationale**:

- **Specialization**: Different agents can build different knowledge bases
- **Controlled sharing**: Only share via turn-aware winner mechanism
- **Scalability**: Single Qdrant database, filtered by metadata
- **Privacy**: Agent-specific knowledge stays private until winning

**Alternative considered**: Shared memory pool for all agents. Rejected because:
- Information overload: Agent sees irrelevant memories from other agents
- Loss of specialization: Can't maintain agent-specific expertise
- Temporal issues: Agent sees work-in-progress from concurrent agents

Why Turn-Aware Memory Filtering?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision**: Filter previous winners' memories by ``{"turn": 1}`` metadata

**Rationale**:

**Prevents temporal leakage**:

.. code-block:: text

   Turn 2 (concurrent):
   - agent_a working... (incomplete)
   - agent_b working... (incomplete)

   Without filtering:
   - agent_a could see agent_b's Turn 2 work-in-progress ❌
   - Leads to confusion, inconsistent state

   With filtering:
   - agent_a only sees agent_b's Turn 1 (complete, winner) ✅
   - Clean separation of concurrent work

**Implementation**: Memories tagged with ``{"turn": N}`` on recording, filtered on retrieval.

.. raw:: html

   </details>

API Reference
-------------

For programmatic usage, see the memory module docstrings:

- ``massgen.memory.PersistentMemory`` - Persistent memory API
- ``massgen.memory.ConversationMemory`` - Conversation memory API
- ``massgen.memory._context_monitor`` - Context monitoring utilities

Examples
--------

See complete examples in:

- ``massgen/configs/memory/gpt5mini_gemini_context_window_management.yaml``
- ``massgen/configs/memory/gpt5mini_high_reasoning_gemini.yaml``

Future Improvements
-------------------

.. note::
   The memory system is production-ready but has several planned enhancements.

Planned Features
~~~~~~~~~~~~~~~~

**1. Chunk-Level Token Tracking**

**Current**: Token counting happens after complete response (message-level)

.. code-block:: text

   [Agent streaming response...]
   → [Response complete]
   → [Count tokens on full message]
   → [Compress if needed]

**Issue**: Can't stop mid-stream if response exceeds budget

**Planned**: Track tokens during streaming, warn agent when approaching limit

.. code-block:: text

   [Agent streaming...]
   → [Token counter: 45K / 50K budget]
   → [Agent sees: "⚠️ Approaching token limit, wrap up"]
   → [Agent concludes early]

**2. Configurable Memory Granularity**

**Planned**: Control what gets recorded to memory

.. code-block:: yaml

   memory:
     recording:
       include_mcp_tools: false       # Skip MCP tools (default)
       include_reasoning: true        # Include reasoning (default)
       include_reasoning_summary: true
       tool_argument_limit: 1000      # Max chars for tool args
       content_filters:
         - "workflow_tools"  # vote, new_answer
         - "system_messages"

**3. MCP Tool Recording (Optional)**

**Currently**: MCP tools (read_file, list_directory) excluded as implementation details

**Planned**: Optional recording with summarization

.. code-block:: yaml

   memory:
     recording:
       include_mcp_tools: true
       mcp_summarization: "aggregate"  # "aggregate", "each", "none"

**Output**:
   - ``aggregate``: "[Tools used: read_file (3x), list_directory (2x)]"
   - ``each``: Full detail per tool
   - ``none``: Current behavior (skip)

**4. Memory Summarization on Compression**

**Current**: Just remove old messages

**Planned**: Generate summary of compressed context

.. code-block:: text

   Compression:
   - Remove messages 1-10
   - Generate summary: "User analyzed MassGen codebase, identified 3 key components..."
   - Inject summary as context for future turns

Known Limitations
~~~~~~~~~~~~~~~~~

**Token Counting During Streaming**

Context is counted **after** response completes, not during streaming chunks. This means:

- ✅ Accurate final count
- ❌ Can't stop mid-response if too large
- ❌ No proactive budget warnings

**Workaround**: Set conservative compression thresholds (50-60%) to leave headroom.

**MCP Tools Not in Memory**

MCP tool executions (read_file, list_directory) are **intentionally excluded** as implementation details.

**Rationale**: The final answer captures what was learned; tool execution trace is noise for semantic memory.

**If you need execution history**: Check orchestrator logs or agent workspace snapshots, not memory.

**Session-Level Memory Isolation**

Memories are isolated per session. To access knowledge from previous sessions, either:
- Set ``session_name: null`` (search all sessions)
- Explicitly continue a session with ``session_name: "my_session"``

**Local Qdrant Single-Agent Only**

File-based Qdrant (``mode: "local"``) does NOT support concurrent access.

**For multi-agent**: Always use ``mode: "server"`` with Docker.

Next Steps
----------

- :doc:`multi_turn_mode` - Interactive multi-turn conversations
- :doc:`orchestration_restart` - Graceful restart handling
- :doc:`logging` - Understanding MassGen's logging system
