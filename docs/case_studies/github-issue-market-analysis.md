# MassGen v0.1.1: Custom Tools with GitHub Issue Market Analysis

MassGen is focused on **case-driven development**. MassGen v0.1.1 introduces a comprehensive custom tools system that enables users to extend agent capabilities with domain-specific Python functions. This case study demonstrates **Self-Evolution through Market Analysis** where agents use custom tools combined with web search to analyze GitHub issues, research market trends, and autonomously drive feature prioritization.

---

# Table of Contents

- [📋 PLANNING PHASE](#planning-phase)
  - [📝 Evaluation Design](#evaluation-design)
    - [Prompt](#prompt)
    - [Baseline Config](#baseline-config)
    - [Baseline Command](#baseline-command)
  - [🔧 Evaluation Analysis](#evaluation-analysis)
    - [Results & Failure Modes](#results--failure-modes)
    - [Success Criteria](#success-criteria)
  - [🎯 Desired Features](#desired-features)
- [🚀 TESTING PHASE](#testing-phase)
  - [📦 Implementation Details](#implementation-details)
    - [Version](#version)
    - [New Features](#new-features)
    - [New Config](#new-config)
    - [Command](#command)
  - [🤖 Agents](#agents)
  - [🎥 Demo](#demo)
- [📊 EVALUATION & ANALYSIS](#evaluation--analysis)
  - [Results](#results)
    - [The Collaborative Process](#the-collaborative-process)
    - [The Voting Pattern](#the-voting-pattern)
    - [The Final Answer](#the-final-answer)
    - [Custom Tool Usage](#custom-tool-usage)
    - [Self-Evolution Demonstrated](#self-evolution-demonstrated)
  - [🎯 Conclusion](#conclusion)
- [📌 Status Tracker](#status-tracker)

---

<h1 id="planning-phase">📋 PLANNING PHASE</h1>

<h2 id="evaluation-design">📝 Evaluation Design</h2>

### Prompt

The prompt tests whether MassGen agents can autonomously analyze their own codebase, GitHub issues, and market trends to drive product development:

```
Analyze the massgen dir and MassGen GitHub issues to understand what features users are requesting. Also research current trends in multi-agent AI systems and LLM orchestration. Based on the existing code, the open issues and market trends, write a prioritized recommendation report for the next release.
```

This prompt requires agents to:
1. Access and analyze the MassGen codebase (via filesystem access)
2. Fetch and analyze GitHub issues (via custom tool)
3. Research market trends (via web search)
4. Synthesize all sources into actionable recommendations

### Baseline Config

Prior to v0.1.1, MassGen lacked a native custom tools system. Users had two main options for extending agents with domain-specific capabilities like GitHub API integration:

- **MCP Servers**: Use Model Context Protocol servers (external process with inter-process communication overhead)
- **Built-in Tools Only**: Rely solely on web search and code execution (limited functionality)

While MCP servers worked, they added operational complexity. There was no simple, **native** way to add Python functions as tools directly within the MassGen process.

### Baseline Command

Pre-v0.1.1 equivalent would require web search only (no custom GitHub tool):

```bash
uv run massgen \
  --config massgen/configs/basic/multi/gemini_gpt5nano_claude.yaml \
  "Research multi-agent AI trends and make recommendations for MassGen's next release."
```

**Limitations**:
- No direct GitHub API access
- No structured issue analysis
- Relies solely on web search scraping
- Cannot combine codebase analysis with issue data

<h2 id="evaluation-analysis">🔧 Evaluation Analysis</h2>

### Results & Failure Modes

Before v0.1.1, users attempting similar tasks would face:

**No Custom Tool Integration**:
- Cannot easily add domain-specific capabilities (GitHub API, database queries, etc.)
- Potentially high friction for extending agent capabilities

**Limited Self-Evolution**:
- No mechanism for agents to programmatically access issue tracker
- Web search provides unstructured data vs. API-structured data
- Cannot reliably analyze engagement metrics (comments, reactions, labels)

**Example Failure**: Asking agents to "analyze GitHub issues" would result in:
- Web search attempting to scrape GitHub web pages (unreliable)
- No access to issue metadata (labels, reactions, comments)
- Incomplete or inaccurate issue categorization

### Success Criteria

1. **Custom Tool System Works**: Users can register Python functions as tools via YAML config
2. **Tool Discovery**: Agents automatically discover and use custom tools
3. **Multi-Source Analysis**: Agents combine custom tools + web search + filesystem access
4. **Structured Data Access**: Custom tool provides structured GitHub issue data
5. **Self-Evolution**: Agents demonstrate market-driven feature prioritization
6. **Multi-Agent Collaboration**: Both agents use custom tools and reach consensus

<h2 id="desired-features">🎯 Desired Features</h2>

With these goals defined, v0.1.1 implements:

- **Custom Tool Registration**: Simple YAML configuration for adding Python functions as tools
- **Automatic Schema Generation**: MassGen generates JSON schemas from function signatures
- **ExecutionResult API**: Standardized return type for tool outputs (text, images, audio)
- **Streaming Support**: Tools can stream progress updates for long-running operations
- **Cross-Backend Support**: Custom tools work with all backends (Gemini, OpenAI, Claude, etc.)
- **GitHub Issue Analyzer Tool**: Reference implementation demonstrating market analysis capability

---

<h1 id="testing-phase">🚀 TESTING PHASE</h1>

<h2 id="implementation-details">📦 Implementation Details</h2>

### Version

**MassGen v0.1.1**

<h3 id="new-features">✨ New Features</h2>

**Custom Tools System**:
- `massgen/tool/` module with `ToolManager` for tool registration and execution
- Automatic JSON schema generation from Python type hints and docstrings
- `ExecutionResult` API for standardized tool outputs
- Support for streaming results with progress updates
- Multimodal outputs (text, images, audio)
- Tool categories for organization
- Built-in tools: `run_python_script`, `run_shell_script`, `read_file_content`, `save_file_content`, `append_file_content`

**GitHub Issue Analyzer Tool** (`massgen/tool/_self_evolution/_github_issue_analyzer.py`):
- Fetches issues from GitHub API with PR filtering
- Analyzes by category, labels, and engagement (comments + reactions)
- Provides insights: top engaged issues, most requested features, category breakdown
- Streaming progress updates during execution
- Demonstrates Self-Evolution through autonomous market analysis

**Configuration Integration**:
- Simple YAML `custom_tools` configuration
- Specify tool path, function name, category, and description
- Works across all backends

### New Config

`massgen/configs/tools/custom_tools/github_issue_market_analysis.yaml`:

```yaml
agents:
  - id: "agent_a"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      cwd: "workspace1"

      custom_tools:
        - name: ["fetch_github_issues"]
          category: "market_analysis"
          path: "massgen/tool/_self_evolution/_github_issue_analyzer.py"
          function: ["fetch_github_issues"]

      enable_web_search: true

  - id: "agent_b"
    backend:
      type: "openai"
      model: "gpt-5-mini"
      cwd: "workspace2"

      text:
        verbosity: "medium"
      reasoning:
        effort: "low"
        summary: "auto"

      custom_tools:
        - name: ["fetch_github_issues"]
          category: "market_analysis"
          path: "massgen/tool/_self_evolution/_github_issue_analyzer.py"
          function: ["fetch_github_issues"]

      enable_web_search: true

orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"
  context_paths:
    - path: "massgen"
      permission: "read"
  voting_sensitivity: "balanced"
  answer_novelty_requirement: "lenient"
  max_new_answers_per_agent: 5
```

### Command

```bash
uv run massgen \
  --config massgen/configs/tools/custom_tools/github_issue_market_analysis.yaml \
  "Analyze the massgen dir and MassGen GitHub issues to understand what features users are requesting. Also research current trends in multi-agent AI systems and LLM orchestration. Based on the existing code, the open issues and market trends, write a prioritized recommendation report for the next release."
```

<h2 id="agents">🤖 Agents</h2>

- **Agent A (agent_a)**: Gemini 2.5 Pro with custom GitHub issue analyzer tool, web search, and read access to `massgen/` codebase
- **Agent B (agent_b)**: GPT-5-mini with low reasoning effort, same custom tool, web search, and codebase access

Both agents have:
- **Custom Tool**: `fetch_github_issues` for analyzing GitHub repository issues
- **Web Search**: Enabled for market research
- **Filesystem Access**: Read-only access to `massgen/` directory for codebase analysis
- **Workspace**: Dedicated working directories (`workspace1`, `workspace2`)

<h2 id="demo">🎥 Demo</h2>

Watch the full demonstration of MassGen v0.1.1 custom tools in action:

[![MassGen v0.1.1 Custom Tools Demo](https://img.youtube.com/vi/eXK_oF177zY/0.jpg)](https://www.youtube.com/watch?v=eXK_oF177zY)

**Click to watch**: [MassGen v0.1.1: Custom Tools with GitHub Issue Market Analysis](https://www.youtube.com/watch?v=eXK_oF177zY)

**Execution Log**: (local, not in repo) `.massgen/massgen_logs/log_20251020_012622/`

**Runtime**: ~11 minutes (01:26:23 - 01:37:XX)

---

<h1 id="evaluation--analysis">📊 EVALUATION & ANALYSIS</h1>

## Results

The v0.1.1 custom tools feature enabled a successful multi-source analysis that would have been more difficult in prior versions.

### The Collaborative Process

**Agent Behavior**:

Both agents followed a comprehensive analysis workflow:

1. **Codebase Analysis**: Used filesystem MCP tools to explore the `massgen/` directory structure
2. **GitHub Issue Analysis**: Used the custom `fetch_github_issues` tool to retrieve and categorize open issues
3. **Market Research**: Used web search to research current trends in multi-agent AI and LLM orchestration
4. **Synthesis**: Combined all three sources into prioritized recommendations

**Coordination Pattern** (from `coordination_table.txt`):

- **Total Coordination Events**: 35 events across 5 coordination rounds
- **Agent A (Gemini)**: Provided 1 answer after analyzing all sources
- **Agent B (GPT-5-mini)**: Provided 4 answers across multiple refinement cycles
- **Restarts**: 9 total restarts (5 by Agent A, 4 by Agent B) demonstrating iterative refinement

### The Voting Pattern

**Voting Summary**:
- **Total Votes Cast**: 2 votes
- **Agent A voted for**: `agent2.2` and `agent2.4` (both Agent B answers)
- **Agent B voted for**: `agent2.4` (self-vote after refinement)

**Voting Rationale** (from logs):

Agent A's vote for `agent2.2`:
> "The agent provided a comprehensive and well-structured..."

Agent A's vote for `agent2.4` (winning answer):
> "Agent 2's answer is exceptionally comprehensive..."

Agent B's vote for `agent2.4`:
> "Comprehensive analysis of code, issues, and market trends..."

**Winner**: Agent B (agent_b) selected as winner with answer `agent2.4`

### Answer Evolution Over Time

One of the most interesting aspects of this execution was watching how Agent B's answers **evolved and improved** through multiple iterations. This demonstrates the value of multi-agent collaboration and iterative refinement.

**Agent B's Answer Progression** (4 iterations):

#### agent2.1 (First Answer) - 01:29:42
**Structure**:
- Starts with "Scope and method"
- Lists key findings from three sources
- Provides prioritized recommendations

**Characteristics**:
- Good breadth, covers all major themes
- 3 priorities: "Plugin/Adapter Registry (MVP)", "Basic Observability", "Orchestration primitives"
- Generic deliverables ("Implement a well-documented plugin interface")
- No executive summary
- **Length**: ~100 lines

**Weakness**: Lacks concrete implementation details and actionable next steps.

---

#### agent2.2 (Second Answer) - 01:30:14
**Improvements**:
- ✅ Added **"Executive summary (one-paragraph)"** at the top
- ✅ Better structure with "What I reviewed and assumptions"
- ✅ More refined priority labels: "MVP → near-term → stretch"
- ✅ More specific examples ("OpenAI-compatible wrapper", "FAISS or Weaviate-lite")
- ✅ Added CLI command examples (`massgen adapters list / install / info`)

**Characteristics**:
- Better organization and structure
- More concrete deliverables
- Still somewhat generic on implementation

**Vote**: Agent A voted for this answer, noting it was "comprehensive and well-structured"

---

#### agent2.3 (Third Answer) - 01:30:53
**Improvements**:
- ✅ Restructured to start with **"What I reviewed (concrete artifacts)"** - more specific
- ✅ Executive summary becomes **"Short executive summary"** - more concise
- ✅ Added **"Blocking gaps"** section - clearer problem statement
- ✅ Better separation of strengths vs. gaps
- ✅ More actionable deliverables

**Characteristics**:
- Clearer structure
- More focused recommendations
- Better gap analysis

---

#### agent2.4 (Fourth Answer - WINNER) - 01:31:32
**Major Improvements**:
- ✅ **Executive summary moved to very top** - optimal information hierarchy
- ✅ Added **concrete API sketches** with Python code examples (`BaseAdapter`, `LLMAdapter`, `VectorStoreAdapter`)
- ✅ Added **minimal logging event schema** (JSON example)
- ✅ Added **roadmap & conservative timeline** (3 months, week-by-week breakdown)
- ✅ Added **effort estimates** (engineer-weeks)
- ✅ Added **success metrics** (short-term, mid-term, long-term)
- ✅ Added **"Immediate next steps I can implement for you"** with specific choices
- ✅ Added **recommendation for what to pick first** with clear rationale
- ✅ Added **minimal acceptance criteria** for each deliverable

**Characteristics**:
- **Length**: ~140 lines (~1.5x longer than first answer)
- **Completeness**: Implementation-ready with code samples
- **Actionability**: Specific next steps and effort estimates
- **Structure**: Professional product roadmap format

**Votes**: Both Agent A and Agent B voted for this answer

---

**Key Insights from Evolution**:

1. **Information Hierarchy Matters**: Moving executive summary to the top (agent2.4) made the answer immediately actionable
2. **Concrete > Abstract**: Adding code examples and specific timelines dramatically improved usefulness
3. **Actionability Wins**: The winning answer provided clear "what to do next" guidance
4. **Refinement Works**: Each iteration built on the previous, adding missing elements

**Why agent2.4 Won**:

From Agent A's final vote:
> "Agent 2's answer is exceptionally comprehensive..."

The winning answer wasn't just longer - it was **implementation-ready**. It provided:
- Concrete API designs (copy-paste ready)
- Realistic timeline (3 months, week-by-week)
- Effort estimates (for resource planning)
- Success metrics (for measuring impact)
- Clear next steps (for immediate action)

This evolution demonstrates how **multi-agent collaboration with voting** drives toward not just correct answers, but **maximally useful** answers.

---

### The Final Answer

**Winner**: Agent B (GPT-5-mini)

**Answer Quality**:

The winning answer demonstrated exceptional synthesis of multiple data sources:

**Executive Summary** (from final answer):
> "Goal: Make MassGen the easiest, safest, and fastest way to build multi-agent LLM orchestrations for experimentation and light production use."
>
> "Highest-impact next-release focus (MVP): (1) stabilize a minimal Adapter/Plugin contract + registry and ship 2–3 official adapters, (2) add structured observability with run/step trace IDs, and (3) ship a lightweight in-process scheduler/task-queue with pause/resume/checkpoint semantics."

**Data Sources Utilized** (from answer):
1. ✅ **Codebase Analysis**: "The massgen code tree (core concepts: agent, planner, executor), adapters, CLI surface, examples, and tests"
2. ✅ **GitHub Issues**: "A snapshot of open GitHub issues and community requests (categorized: adapters, observability, orchestration, docs, examples)"
3. ✅ **Market Trends**: "Current market trends in multi-agent/LLM orchestration: growth of adapters/plugin ecosystems, demand for observability/traceability, lightweight orchestration..."

**Prioritized Recommendations**:

The answer provided a detailed roadmap with:
- **Top User Request Themes**: Adapter/Plugin system (high), Observability (high), Orchestration primitives (high)
- **Codebase Strengths and Gaps**: Identified modular core as strength, lack of adapter contract as gap
- **Priority 1 (MVP)**: Adapter API, Structured Observability, Lightweight Scheduler
- **Priority 2 (Near-term)**: Example apps, Reproducibility, Cost-aware routing
- **Priority 3 (Strategic)**: Replay UI, Security/governance, Autoscaling

**Concrete Deliverables**:

The answer included implementation-ready artifacts:
- Python API sketches for `BaseAdapter`, `LLMAdapter`, `VectorStoreAdapter`
- `AdapterRegistry` usage examples
- JSON logging event schema
- 3-month timeline with effort estimates
- Acceptance criteria for each deliverable

### Custom Tool Usage

**Tool Registration** (from logs):
```
01:26:23 | INFO | Registered custom tool: fetch_github_issues from massgen/tool/_self_evolution/_github_issue_analyzer.py (category: market_analysis, desc: 'Fetch and analyze GitHub issues for market-driven ...')
```

**Tool Discovery** (from logs):
```
01:26:24 | INFO | Stream chunk [content]: 🔧 Custom Tool: Custom tools initiated (1 tools available): custom_tool__fetch_github_issues
01:26:30 | INFO | 🔍 [DEBUG] Available custom tools: ['custom_tool__fetch_github_issues']
```

**Evidence of Use**:

The final answer explicitly references GitHub issue analysis:
- "A snapshot of open GitHub issues and community requests (categorized: adapters, observability, orchestration, docs, examples)"
- Categorization by theme matches custom tool output format
- Engagement-based prioritization aligns with tool's analysis capabilities

**Comparison**: Without the custom tool, agents would have attempted web search scraping, which would have:
- Failed to access issue metadata (labels, reactions, comments)
- Provided unstructured, incomplete data
- Lacked reliable categorization and engagement analysis

### Self-Evolution Demonstrated

**Self-Evolution through Market Analysis** ✅

This case study demonstrates how MassGen can autonomously drive its own product roadmap through:

1. **User Feedback Analysis**: Custom tool fetches and categorizes GitHub issues to understand user needs
2. **Market Intelligence**: Web search provides competitive landscape and trend analysis
3. **Codebase Understanding**: Filesystem access enables gap analysis between current state and user needs
4. **Data-Driven Prioritization**: Synthesis of all sources produces actionable, prioritized recommendations
5. **Implementation-Ready Output**: Provides concrete API designs, timelines, and acceptance criteria

**Self-Evolution Pipeline**:
```
GitHub Issues (User Needs)
    + Market Trends (Competitive Landscape)
    + Codebase Analysis (Current Capabilities)
    → Prioritized Feature Roadmap
    → Implementation Artifacts
```

<h2 id="conclusion">🎯 Conclusion</h2>

### Why Custom Tools Enable Self-Evolution

The v0.1.1 custom tools feature is transformative for self-evolution because it:

1. **Lowers Integration Barrier**: Users can add domain-specific capabilities with small amount of Python code
2. **Enables Data Access**: Custom tools provide structured API access (vs. unstructured web scraping)
3. **Maintains Type Safety**: Automatic schema generation from type hints ensures correctness
4. **Works Everywhere**: Cross-backend compatibility means tools work with any model
5. **Composes with Existing Tools**: Custom tools + web search + filesystem = powerful synthesis

### Broader Implications

**For MassGen Development**:
- This case study indicates MassGen can now autonomously analyze user feedback
- Aspects of market-driven development can become automated, not manual
- Product roadmap can be continuously refined based on real-world data

**For MassGen Users**:
- Extend agents with proprietary APIs (databases, internal tools, etc.)
- Build domain-specific workflows without modifying MassGen core
- Combine multiple data sources for comprehensive analysis

### Comparison to Baseline

| Capability | Pre-v0.1.1 | v0.1.1 Custom Tools |
|------------|-----------|-------------------|
| GitHub Issue Analysis | ❌ Web scraping only | ✅ Structured API access |
| Multi-Source Synthesis | ⚠️ Limited (web + code) | ✅ Comprehensive (API + web + code) |
| Extension Mechanism | ❌ Requires backend impl | ✅ Simple Python function |
| Type Safety | ❌ Manual validation | ✅ Automatic from hints |
| Cross-Backend | ❌ Backend-specific | ✅ Works everywhere |
| Self-Evolution | ⚠️ Basic (web research only) | ✅ Advanced (API + analysis) |

### Success Metrics

✅ **Custom Tool System Works**: Tool registered and discovered correctly

✅ **Tool Discovery**: Agents found and used `custom_tool__fetch_github_issues`

✅ **Multi-Source Analysis**: Combined GitHub API + web search + filesystem

✅ **Structured Data Access**: Tool provided categorized, engagement-ranked issues

✅ **Self-Evolution**: Produced actionable, data-driven product roadmap

✅ **Multi-Agent Collaboration**: Both agents used tools; consensus reached via voting

### Next Steps for Self-Evolution

This case study demonstrates **market-driven self-evolution**. The custom tools system enables progression to more advanced capabilities, which will be explored in future versions:

- **Autonomous PR Submission**: Creating GitHub PRs with agent-proposed features
- **Autonomous Code Review**: Running tests, linters, and code analysis on agent PRs
- **Full Development Loop**: Complete autonomous cycle (identify need → implement → test → submit → review)

---

<h3 id="status-tracker">📌 Status Tracker</h3>

- [x] Planning phase completed
- [x] Features implemented
- [x] Testing completed
- [x] Demo recorded (execution log available)
- [x] Results analyzed
- [x] Case study documented