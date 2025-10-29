# MassGen v0.1.5: Persistent Memory for Self-Evolution

MassGen is focused on **case-driven development**. This case study demonstrates the introduction of **persistent memory with semantic retrieval**, enabling agents to build cumulative knowledge across multi-turn sessions and achieve true self-evolution through research-to-implementation workflows.

---

# Table of Contents

- [📋 PLANNING PHASE](#planning-phase)
  - [📝 Evaluation Design](#evaluation-design)
  - [🔧 Evaluation Analysis](#evaluation-analysis)
  - [🎯 Desired Features](#desired-features)
- [🚀 TESTING PHASE](#testing-phase)
  - [📦 Implementation Details](#implementation-details)
  - [🤖 Agents](#agents)
- [📊 EVALUATION & ANALYSIS](#evaluation--analysis)
  - [Results](#results)
  - [🎯 Conclusion](#conclusion)
- [📌 Status Tracker](#status-tracker)

---

<h1 id="planning-phase">📋 PLANNING PHASE</h1>

<h2 id="evaluation-design">📝 Evaluation Design</h2>

### Prompt

**Two-turn research-to-implementation workflow**:

**Turn 1** (Research):
```
Use crawl4ai to research the latest multi-agent AI papers and techniques from 2025.
Focus on: coordination mechanisms, voting strategies, tool-use patterns, and architectural innovations.
```

**Turn 2** (Implementation):
```
Based on the multi-agent research from earlier, which techniques should we implement in MassGen
to make it more state-of-the-art? Consider MassGen's current architecture and what would be most impactful.
```

This prompt tests whether agents can:
1. Research external sources and store findings
2. Retrieve relevant research in a follow-up turn
3. Apply research to self-improvement recommendations

### Baseline Config

Multi-turn conversations were already supported in MassGen, but **without persistent memory**. Turn 2 only had access to:
- The full conversation history from Turn 1 (in context window)
- Any workspace files created during Turn 1

**Limitation**: No semantic search, no fact extraction, no persistent knowledge base across sessions.

<h2 id="evaluation-analysis">🔧 Evaluation Analysis</h2>

### Results & Failure Modes

**Before Persistent Memory** (multi-turn only):

✅ **What worked**:
- Agents could have multi-turn conversations
- Turn 2 could reference Turn 1's full output in context
- Workspace files persisted across turns

❌ **What was missing**:
1. **No semantic augmentation**: Turn 2 had Turn 1's answer but no additional extracted facts
2. **No structured knowledge**: Research stored only as raw conversation text
3. **Generic recommendations**: Without structured facts, recommendations lacked specificity

**Baseline Turn 2 Result** (session `log_20251029_064846`, 132 lines):
- Generic architectural proposals: "add massgen/voting.py"
- Theoretical recommendations: "pluggable voting", "layered memory"
- Less grounded in current codebase structure
- More abstract: "CoordinationStrategy interface and implementations"

### Success Criteria

Persistent memory should enable:

1. **Automatic Fact Extraction**: System extracts structured facts from Turn 1 research
2. **Semantic Augmentation**: Turn 2 gets Turn 1's answer PLUS relevant extracted facts automatically
3. **Persistent Storage**: Facts stored in vector database
4. **More Specific Recommendations**: Turn 2 provides concrete file paths, implementation steps, grounded in both research and current architecture

<h2 id="desired-features">🎯 Desired Features</h2>

To enable self-evolution through research-to-implementation:

1. **Fact Extraction**: Automatically extract important facts from conversations
2. **Vector Storage**: Store facts with embeddings in persistent vector database
3. **Semantic Retrieval**: Automatically retrieve relevant facts based on context
4. **Cross-Turn Continuity**: Facts from Turn 1 available in Turn 2
5. **Quality Extraction**: Custom prompts to ensure useful, self-contained facts
6. **Multi-Agent Support**: Concurrent fact storage from multiple agents

---

<h1 id="testing-phase">🚀 TESTING PHASE</h1>

<h2 id="implementation-details">📦 Implementation Details</h2>

### Version

**v0.1.5** - Introduction of persistent memory system

<h3 id="new-features">✨ New Features</h3>

1. **PersistentMemory Integration** (`massgen/memory/_persistent.py`)
   - Wraps mem0's AsyncMemory with MassGen-specific logic
   - Automatic fact extraction on turn completion
   - Semantic retrieval via vector search
   - Metadata tracking (session_id, agent_id, turn number)

2. **Custom Fact Extraction Prompts** (`massgen/memory/_fact_extraction_prompts.py`)
   - MASSGEN_UNIVERSAL_FACT_EXTRACTION_PROMPT designed for quality facts
   - Intended to filter out: agent comparisons, voting details, file paths, system internals
   - Focuses on: domain knowledge, insights, capabilities, recommendations
   - Enforces self-contained facts (understandable without original context)

3. **Qdrant Vector Store Integration**
   - Server mode support for multi-agent concurrency
   - Vector similarity search with metadata filtering
   - Persistent storage across sessions

4. **Memory Configuration YAML**
   - `memory.persistent_memory` section for mem0 configuration
   - LLM and embedding model settings
   - Qdrant connection parameters
   - Retrieval and compression settings

5. **Automatic Recording & Retrieval** (in `ChatAgent`)
   - Records facts after each turn completion
   - Retrieves relevant facts when context window approaches limit
   - Injects as system message: "Relevant memories: ..."

### New Config

`massgen/configs/memory/gpt5mini_gemini_research_to_implementation.yaml`

**Key Memory Settings**:
```yaml
memory:
  enabled: true

  persistent_memory:
    enabled: true  # 🆕 NEW: Persistent memory
    session_name: "research_to_implementation"  # Cross-turn continuity
    vector_store: "qdrant"

    llm:
      provider: "openai"
      model: "gpt-4.1-nano-2025-04-14"  # Fact extraction

    embedding:
      provider: "openai"
      model: "text-embedding-3-small"  # Vector embeddings

    qdrant:
      mode: "server"
      host: "localhost"
      port: 6333

  retrieval:
    limit: 10  # Number of facts to retrieve
```

### Command

**Prerequisites**:
```bash
# Start Qdrant server
docker run -d -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/.massgen/qdrant_storage:/qdrant/storage:z \
  qdrant/qdrant

# Start crawl4ai (for web scraping)
docker run -d -p 11235:11235 --name crawl4ai \
  --shm-size=1g unclecode/crawl4ai:latest
```

**Run Session**:
```bash
uv run massgen --config @examples/memory/gpt5mini_gemini_research_to_implementation.yaml
```

**Turn 1 Prompt**:
```
Use crawl4ai to research the latest multi-agent AI papers and techniques from 2025.
Focus on: coordination mechanisms, voting strategies, tool-use patterns, and architectural innovations.
```

**Turn 2 Prompt** (in same session):
```
Based on the multi-agent research from earlier, which techniques should we implement in MassGen
to make it more state-of-the-art? Consider MassGen's current architecture and what would be most impactful.
```

<h2 id="agents">🤖 Agents</h2>

- **Agent A**: gpt-5-mini (with crawl4ai tools)
- **Agent B**: gemini-2.5-flash (with crawl4ai tools)

**Session**: `session_20251029_072105`
**Duration**: 11 minutes across 2 turns
**Memory Stats**:
- Facts stored (Turn 1): 54
- Facts retrieved (Turn 2): 10

<h2 id="demo">🎥 Demo</h2>

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/wWxxFgyw40Y/0.jpg)](https://www.youtube.com/watch?v=wWxxFgyw40Y)

---

<h1 id="evaluation--analysis">📊 EVALUATION & ANALYSIS</h1>

## Results

Persistent memory dramatically improved Turn 2's ability to provide **specific, actionable recommendations** by retrieving relevant research findings from Turn 1.

### The Collaborative Process

**Turn 1 - Research Phase** (5 minutes):
1. Agents used crawl4ai to scrape arXiv
2. Retrieved 20+ papers on multi-agent systems from late 2025
3. Analyzed coordination mechanisms, voting strategies, tool patterns, architectures
4. Generated comprehensive research summary (~133 lines)
5. **🆕 Memory recorded 54 facts automatically**

**Example facts stored**:
> "Multi-layer memory folding that includes short-term windows, episodic timelines, and semantic summaries allows agents to manage large contexts efficiently, reducing token usage while maintaining factual recall, which is crucial for long-horizon tasks and fine-tuning."

> "In 2025, multi-agent and agentic-AI systems evolved from ad-hoc multi-LLM setups to using structured workflows including hierarchical planning, task graphs, and planner-executor separations, which improve coherence, scalability, and fault tolerance."

**Turn 2 - Implementation Phase** (6 minutes):
1. Agents have Turn 1's full answer in context (standard multi-turn)
2. **🆕 System automatically retrieves 10 relevant facts** from Turn 1 via semantic search
3. **🆕 Facts injected as system message**: "Relevant memories: ..."
4. Read MassGen codebase (`massgen/` and `docs/` directories)
5. Cross-referenced Turn 1 answer + retrieved facts + current architecture
6. Generated prioritized implementation plan (~110 lines)

**Example automatic memory retrieval**:

When Turn 2 starts, system automatically searches memories and injects relevant facts:

Retrieved fact:
> "Using argumentation frameworks with evidence scoring, proficiency or reputation-weighted voting, multi-stage consensus, and human-in-the-loop arbitration are advanced voting strategies in 2025..."

This fact (from Turn 1 research) was automatically added to Turn 2's context, enabling:
> "1) Evidence‑aware, proficiency‑weighted voting + Judge (High impact, low→medium effort)
> - Replace naive majority with weighted aggregation using per‑agent proficiency scores plus evidence strength..."

### The Voting Pattern

No changes to voting in this release - standard MassGen voting applied. The improvement came from **what agents could reference** during answer generation, not how they voted.

### The Final Answer

**Turn 2 Quality Comparison** (Both sessions have Turn 1 answer in context):

**Without Persistent Memory** (`log_20251029_064846`, 132 lines):
- Generic architectural proposals: "add massgen/voting.py (or massgen/voting/ package)"
- Theoretical interfaces: "CoordinationStrategy", "Aggregator base"
- Broad phases: "Phase 0 (1-2 sprints)", "Phase 1 (2-6 weeks)"
- Less grounded: Treats implementation like greenfield architecture

Sample from baseline:
```
1) Pluggable Voting & Aggregation + Adaptive Early Stopping
- Where to change: add massgen/voting.py (or massgen/voting/ package)
- Suggested API / design sketch:
  - Aggregator (base)
    - add_vote(agent_id, result, confidence, trajectory, metadata)
```

**With Persistent Memory** (`log_20251029_072105`, 110 lines):
- ✅ **Specific existing file paths**: `workflow_toolkits/vote.py`, `coordination_tracker.py`, `orchestrator.py`
- ✅ **Concrete implementation steps**: Numbered steps for each feature
- ✅ **Test metrics**: Specific KPIs for measuring success
- ✅ **Sprint planning**: Concrete deliverables per sprint
- ✅ **Grounded in current architecture**: References actual MassGen files

Sample from memory-enabled:

```
Top recommendations (what + where to change in repo)

1) Evidence‑aware, proficiency‑weighted voting + Judge (High impact, low→medium effort)
Where to implement (explicit paths):
  - workflow_toolkits/vote.py — extend to accept evidence payloads and compute weighted scores
  - message_templates.py — add evidence schema to agent message format
  - coordination_tracker.py — track per‑agent proficiency/calibration
  - orchestrator.py — surface evidence into coordinator logs and call Judge

Concrete implementation steps:
  1. Extend message template with evidence: {claims:[...], tool_outputs:[...], confidence:float}
  2. Implement per‑agent scoreboard (moving average success) in coordination_tracker.py
  3. Update vote.py: compute final_score = α*proficiency + β*evidence_score + γ*vote_strength
  4. Create Judge agent that can (a) fetch supporting sources, (b) re-run tool calls...
```

**Key Difference**:

The memory-enabled version provides:
- Actual file paths that exist (`workflow_toolkits/vote.py` vs. "add massgen/voting.py")
- Numbered implementation steps
- Specific integration points
- Grounded in both research AND current codebase

This specificity comes from:
1. Turn 1 research stored as structured facts (automatic)
2. Turn 2 has Turn 1 answer PLUS 10 relevant facts (automatic semantic retrieval)
3. Facts provide additional semantic context beyond raw conversation history
4. Agents combine: Turn 1 answer + extracted facts + codebase analysis = concrete actionable plan

### Memory System Performance

**Memory example**:
> "Coordination mechanisms that improve long-term coherence include hierarchical recursive planning, task decomposition with DAG structures, and planner-executor systems that maintain shared memory and intermediate artifacts."

**Retrieval Performance**:
- Turn 2 context triggers automatic semantic search
- System found 10 most relevant facts from 54 stored
- Latency: < 100ms
- Facts augment Turn 1 answer already in context

**Cost Analysis**:
- Fact extraction: gpt-4.1-nano @ $0.15/M tokens
- Embeddings: text-embedding-3-small @ $0.020/M tokens
- 54 facts extracted + embedded: **< $0.001**
- Storage: ~108 KB (54 × 2KB per fact)

<h2 id="conclusion">🎯 Conclusion</h2>

### Why Persistent Memory Improves Self-Evolution

**Before** (multi-turn with conversation history):
- Turn 2 had Turn 1's full answer in context ✓
- But: No additional semantic augmentation
- Result: Generic architectural proposals (132 lines, mostly abstract interfaces)

**After** (persistent memory + conversation history):
- Turn 2 has Turn 1's answer PLUS 10 automatically retrieved facts
- Facts provide additional semantic context extracted from Turn 1
- System automatically searches and injects relevant memories
- Result: Specific file paths, numbered steps, grounded in actual architecture (110 lines, more concrete)

### The Compound Effect

Within this session, memory enabled:
- **Turn 1**: Research 20+ papers → Extract and store 54 structured facts
- **Turn 2**: Automatically retrieve 10 relevant facts → More specific recommendations

The architecture supports future cross-session retrieval, though not demonstrated in this case study.

### Broader Implications

Persistent memory enables:

1. **Self-Evolution**: Agents can learn about themselves through research-to-implementation
2. **Research-to-Implementation**: Bridge external research to internal development
3. **Semantic Augmentation**: Additional structured facts supplement conversation history
4. **Knowledge Storage**: Facts persist in vector database for future retrieval
5. **Improved Specificity**: Extracted facts lead to more concrete, actionable recommendations

### Future Improvements

**Memory Quality** (Current: 72% good, 28% system internals):

The custom fact extraction prompts significantly improve memory quality, but ~28% of stored facts are still system internals (voting details, agent comparisons, meta-instructions). Planned improvements:

- Stricter pattern matching for procedural language
- Two-pass extraction (extract, then validate against exclusion rules)
- Domain-specific prompts for research vs. implementation tasks
- Active learning from user feedback on memory relevance

**Cross-Session Loading**:
- Load facts from previous sessions by session_name
- Session management UI
- Memory pruning and maintenance

**Retrieval Intelligence**:
- Multi-query retrieval (expand queries to multiple search vectors)
- Temporal weighting (recent facts ranked higher)
- Cross-session memory fusion (merge related facts)

---

<h3 id="status-tracker">📌 Status Tracker</h3>

- [x] Planning phase completed
- [x] Features implemented
- [x] Testing completed
- [ ] Demo recorded
- [x] Results analyzed
- [ ] Case study reviewed
