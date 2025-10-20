# MassGen v0.0.29: MCP Planning Mode for Safe Tool Coordination

MassGen is focused on **case-driven development**. MassGen v0.0.29 introduces MCP Planning Mode, a strategic coordination approach that allows agents to plan MCP tool usage without execution during collaboration, preventing irreversible actions like sending messages or modifying external systems until consensus is reached. This case study demonstrates how planning mode enables safe multi-agent collaboration with external integrations like Discord.

## 🤝 Contributing
To guide future versions of MassGen, we encourage **anyone** to submit an issue using the corresponding `case-study` issue template based on the "PLANNING PHASE" section found in this template.

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
    - [Final Results & Answer Comparison](#final-results--answer-comparison)
    - [Anything Else](#anything-else)
  - [🎯 Conclusion](#conclusion)
- [📌 Status Tracker](#status-tracker)

---

<h1 id="planning-phase">📋 PLANNING PHASE</h1>

<h2 id="evaluation-design">📝 Evaluation Design</h2>

### Prompt
The prompt tests whether MassGen can safely handle MCP tool usage (Discord messaging) in a multi-agent scenario without causing duplicate or premature executions:

```bash
Please read https://github.com/Leezekun/MassGen/issues/276 and send a message to the 'MassGen Testing Server' Discord server in the general channel with a summary and implementation next steps to notify the team of your approach. The guild ID is 1417773298309136445 and channel ID is 1417773298837880906
```

### Baseline Config
Prior to v0.0.29, MassGen agents with MCP tool access would execute tools immediately during coordination, leading to duplicate messages, premature actions, and no rollback capability for irreversible operations.

A baseline would use MCP without planning mode, where agents execute tools during coordination.

### Baseline Command
```bash
# Pre-v0.0.29: No planning mode - agents execute tools immediately
# Would cause multiple Discord messages during coordination
uv run python -m massgen.cli \
  --config massgen/configs/tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml \
  "Please read https://github.com/Leezekun/MassGen/issues/276 and send a message to Discord..."
```

<h2 id="evaluation-analysis">🔧 Evaluation Analysis</h2>

### Results & Failure Modes

Before v0.0.29, users attempting multi-agent workflows with MCP tools (Discord, Twitter, Notion, etc.) would face:

**Duplicate External Actions:**
- Each agent executing Discord/Twitter/Slack messages during coordination
- Multiple redundant notifications flooding channels
- No way to prevent premature execution before consensus

**Cannot Safely Collaborate on Communication Tasks:**
- Users must choose between multi-agent quality OR safe MCP usage
- Manual intervention needed to prevent duplicate actions

### Success Criteria
1. **Safe Tool Planning**: Agents can plan MCP tool usage without execution during coordination
2. **Consensus Before Execution**: Only the winning agent executes tools in final presentation
3. **Multi-Agent Quality Preserved**: Full collaboration benefits (debate, refinement, voting) maintained
4. **Multi-Backend Support**: Planning mode works across Response API, Chat Completions, and Gemini backends
5. **Transparent Planning**: Users can see planned tool calls in agent answers

<h2 id="desired-features">🎯 Desired Features</h2>

With these goals defined, the next step was to design a system that separates tool planning from execution.
- **Coordination Configuration**: New `CoordinationConfig` class with `enable_planning_mode` flag
- **Backend Planning Support**: Planning mode implementation for Response API, Chat Completions, and Gemini
- **Tool Execution Control**: Defer MCP tool execution until final presentation phase
- **Plan Visibility**: Display planned tool calls in agent answers without executing them
- **Winner-Only Execution**: Only the selected winner executes their planned tools

---

<h1 id="testing-phase">🚀 TESTING PHASE</h1>

<h2 id="implementation-details">📦 Implementation Details</h2>

### Version
MassGen v0.0.29 (October 8, 2025)

<h3 id="new-features">✨ New Features</h3>

The MCP Planning Mode was realized through a **coordination-level configuration system** that controls tool execution timing. The implementation consists of three core components:

**1. Coordination Configuration**

A new `CoordinationConfig` class enables planning mode at the orchestrator level:
- `enable_planning_mode` flag controls whether agents execute tools during coordination
- Applied uniformly across all agents in the coordination phase
- Automatically switches to execution mode for the winning agent's final presentation

**2. Multi-Backend Planning Support**

Planning mode implementation across multiple backends:
- **Response API Backend**: Full planning mode with tool call simulation
- **Chat Completions Backend**: Unified planning across OpenAI-compatible APIs
- **Gemini Backend**: Native Gemini planning mode support
- Consistent behavior: agents see tool calls in context without execution

**3. Execution Phase Control**

Strategic tool execution management:
- **During Coordination**: Agents describe what they would do (planning only)
- **Final Presentation**: Winner agent executes their planned tools
- **Safety Guarantee**: Prevents duplicate messages, notifications, or modifications

**Additional v0.0.29 improvements** include:
- **File Operation Safety**: Read-before-delete enforcement via `FileOperationTracker`
- **Enhanced MCP Tool Filtering**: Multi-level filtering with backend and per-server control
- **Comprehensive Test Coverage**: `test_mcp_blocking.py` and `test_gemini_planning_mode.py`

See the full [v0.0.29 release notes](https://github.com/Leezekun/MassGen/releases/tag/v0.0.29) for complete details.

### New Config

Configuration file: [`massgen/configs/tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml)

Key breakthrough - **`enable_planning_mode` prevents tool execution during coordination**:

```yaml
# NEW: Planning mode configuration
orchestrator:
  coordination:
    enable_planning_mode: true  # Agents plan tools without execution during coordination
```

**Key Innovation**: System message explicitly instructs agents to provide content first, execute tools only in final presentation. Combined with `enable_planning_mode`, this prevents premature execution!

### Command
```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml \
  "Please read https://github.com/Leezekun/MassGen/issues/276 and send a message to the 'MassGen Testing Server' Discord server in the general channel with a summary and implementation next steps to notify the team of your approach. The guild ID is 1417773298309136445 and channel ID is 1417773298837880906"
```

<h2 id="agents">🤖 Agents</h2>

- **Agent A (claude_code_discord_mcp)**: Claude Code with Discord MCP server
  - Backend: Claude Code (native SDK)
  - MCP Server: Discord (mcp-discord package)
  - Special capabilities: Built-in tools (Read, Write, Bash, WebSearch) + Discord integration
  - Planning Mode: Tool calls visible in answers but not executed during coordination

- **Agent B (gpt-5-mini)**: OpenAI GPT-5-mini with reasoning and web search
  - Backend: OpenAI (Chat Completions API)
  - Model: gpt-5-mini with medium reasoning effort
  - Special capabilities: Web search, code interpreter
  - Planning Mode: Full collaboration without premature tool execution

Both agents participate in MassGen's collaborative consensus mechanism with planning mode ensuring safe tool usage.

<h2 id="demo">🎥 Demo</h2>

Watch the v0.0.29 MCP Planning Mode in action:

[![MassGen v0.0.29 MCP Planning Mode Demo](https://img.youtube.com/vi/jLrMMEIr118/0.jpg)](https://youtu.be/jLrMMEIr118)

Key artifacts from the case study run:
- Both agents researched GitHub issue #276 and created Discord message plans
- **No duplicate messages** during coordination (planning mode working)
- Agent B selected as winner after 3 restarts (2 from Agent B, 1 from Agent A)
- **Only Agent B executed** Discord message in final presentation
- Message successfully posted to Discord channel 1417773298837880906

---

<h1 id="evaluation--analysis">📊 EVALUATION & ANALYSIS</h1>

## Results

The v0.0.29 MCP Planning Mode successfully achieved all success criteria and demonstrated safe multi-agent collaboration with external integrations:

✅ **Safe Tool Planning**: Both agents created Discord message plans without execution during coordination

✅ **Consensus Before Execution**: Only Agent B (winner) executed Discord tool in final presentation

✅ **Multi-Agent Quality Preserved**: Full collaboration with 3 restarts, voting, and refinement cycles

✅ **Multi-Backend Support**: Claude Code and OpenAI backends both supported planning mode

✅ **Transparent Planning**: Agents' answers showed planned Discord message content and tool invocations

### The Collaborative Process

**How agents collaborated with v0.0.29 MCP Planning Mode:**

**Understanding Answer Labels:**
MassGen uses a labeling system `agent{N}.{attempt}` where:
- **N** = Agent number (1, 2, etc.)
- **attempt** = Answer iteration number (increments after each restart/refinement)

For example:
- `agent2.1` = Agent 2's 1st answer
- `agent1.1` = Agent 1's 1st answer
- `agent2.final` = Agent 2's final answer as the winner

**Multi-Round Refinement Pattern:**
The coordination log reveals efficient collaboration with planning mode:
- **Total restarts**: 3 (Agent A: 1 restart, Agent B: 2 restarts)
- **Total answers**: 2 answers (agent1.1, agent2.1)
- **Voting rounds**: Both agents voted for Agent B's answer

**Agent A (Claude Code) - Detailed Planning Approach:**
1. **Initial answer (agent1.1)**:
   - Read GitHub issue #276 via web search
   - Created comprehensive implementation plan with MVP scope, tech choices, concrete tasks, security considerations, and timeline
   - **Planned Discord message** (ready to post but not executed)
   - Explicitly noted: "When you want me to post this to the server, I will call the Discord post API"
2. **Restart 1**: After seeing Agent B's answer, voted for Agent B
3. **Final status**: Completed without executing tools

**Agent B (GPT-5-mini) - Concise Planning Approach:**
1. **Initial answer (agent2.1)**:
   - Read GitHub issue #276 via web search
   - Created MVP-first implementation plan with architecture, sprint estimates, risks/mitigations
   - **Planned Discord message** (shorter, more actionable)
   - Noted: "After you confirm the message, I will post it"
2. **Restart 1**: Invalid vote triggered restart (new answer appeared)
3. **Restart 2**: Voted for own refined answer (agent2.1)
4. **Final presentation**: **Executed Discord tool** - message successfully posted to channel

**Key v0.0.29 improvement**: Planning mode prevented both agents from sending duplicate Discord messages during coordination. Only the winner executed tools after consensus was reached.

### The Voting Pattern

**Planning Mode Voting Dynamics:**

The coordination table shows clean voting behavior enabled by planning mode:

1. **Agent A (Claude Code) voting behavior:**
   - Voted for Agent B's answer (agent2.1)
   - Reasoning: "Agent2 provided a clear, concise summary, a practical MVP-first implementation plan, a ready-to-post Discord message, and sensible next steps and calls to action—fully addressing the user's request and ready for posting with minimal edits."

2. **Agent B (GPT-5-mini) voting behavior:**
   - Initially voted for itself but vote invalidated due to new answer
   - After restart 2, voted for itself (agent2.1)
   - Reasoning: "Clear, concise summary and implementation plan with concrete MVP, sprint estimates, risks/mitigations, and a ready-to-post Discord message. Actionable call to action and follows the user's request to await approval before posting."

3. **Winner selection:**
   - Agent B (GPT-5-mini) selected as winner
   - Both agents voted for Agent B in final round
   - Agent B executed Discord message in final presentation

**Key v0.0.29 improvement**: Planning mode allowed agents to evaluate each other's planned Discord messages without risk of duplicate executions, leading to informed voting decisions.

### Final Results & Answer Comparison

**Winner: Agent B (gpt-5-mini) - GPT-5-mini with Planning Mode**

To provide concrete evidence of how planning mode works, here are the actual answers from both agents:

**Agent A's Answer (agent1.1):**
- Comprehensive planning approach with detailed sections
- Structured implementation plan: MVP scope, tech choices, 6 concrete tasks, security considerations
- Explicit Discord message prepared but **not executed** during coordination
- Clear notation: "When you want me to post this to the server, I will call the Discord post API"
- Longer, more detailed message with timeline estimates (Oct 9 - Oct 30, 2025)

<details>
<summary><u>📄 Agent A (Claude Code) - Answer (agent1.1)</u></summary>

```
Planning / intended actions

1) What I did: I opened and read the referenced GitHub issue ([FEATURE] Web UI for MassGen, issue #276) to capture the requirements and proposed implementation notes. (I used the issue contents to prepare the summary and next steps below.)

2) What I will do next (execution plan):
   - Post a concise summary + implementation next-steps message into the MassGen Testing Server -> #general (guildId 1417773298309136445, channelId 1417773298837880906).
   - If you want, after posting I can create a project/board and open initial skeleton PRs (frontend skeleton + backend CLI adapter) and assign the tasks.
   - For posting, I will use the Discord send API once I have permission/credentials in the execution phase.

Analysis of other agents' proposals

- No other agent proposals were available to compare; I prepared the message based directly on the issue contents.

Prepared message to post in #general (exact text)

Heads-up: New feature request opened on Oct 2, 2025 — "[FEATURE] Web UI for MassGen" (issue #276).

Summary:
- Goal: Build a lightweight web UI to run, monitor, and visualize MassGen multi-agent coordination workflows (make MassGen accessible beyond CLI).
- Key features proposed: prompt/config input, a grid of agent cards (logs, status, insights), orchestrator panel (strategy + logs), voting/comparison view, timeline/visual log, config upload and export, real-time streaming updates.
- Suggested stack & architecture: frontend in React/Next.js (Tailwind ok), backend that exposes MassGen CLI via API, real-time updates via WebSockets or SSE. Mockups are attached in the issue.

Implementation next steps (proposed MVP + tasks):
1) Define MVP scope (2-week sprint recommended):
   - MVP features: Run/Stop from UI; agent cards with live logs/status; basic voting view; upload demo_config.yaml; stream logs via WebSocket.
2) Tech choices & infra (decide early):
   - Frontend: React + Next.js + Tailwind (or your preference)
   - Backend: Node/Express (or FastAPI) adapter that runs MassGen CLI commands and exposes REST + WebSocket endpoints
   - Packaging: Dockerize both frontend and backend for easy deployment and local dev
3) Concrete tasks (suggested owners):
   - Frontend skeleton + Run UI (owner: frontend)
   - Backend CLI adapter & API endpoints (owner: backend)
   - WebSocket log stream + orchestration state model (owner: backend)
   - Voting UI + agent comparison (owner: frontend)
   - Sample demo_config.yaml + demo workflow for testing (owner: dev/test)
   - CI / Docker images + basic deployment (owner: infra)
4) Security & reliability considerations:
   - Process isolation for agent runs (containers or sandboxing)
   - Auth for API/UI (token-based) and rate-limiting
   - Logging, observability, and tests for the adapter
5) Timeline (proposal):
   - Start: Oct 9, 2025
   - MVP completion: Oct 23, 2025
   - Demo + docs: Oct 30, 2025
   (These are estimates — adjust based on volunteer availability.)

Call to action / questions:
- Who can volunteer to own frontend / backend / infra for the MVP sprint? Please reply with names so I can add assignees.
- If we agree on the tech stack, I will create a project board and issue checklist, then open the initial skeleton PRs.

Source: GitHub issue #276 (feature description, proposed UI and implementation suggestions).

Notes about execution

- When you want me to post this to the server, I will call the Discord post API with channelId 1417773298837880906 and the exact message above. If you'd like any changes to wording, scope, or timeline, tell me now and I'll adjust before posting.
- If you want me to go ahead immediately and I have the necessary permissions, I will send the message and report back with the message ID and any replies.

--------------------------------------------------------------------------------

Suggested mcp__discord__discord_send invocation (for execution phase)
- channelId: "1417773298837880906"
- message: (the exact message text shown above)

If you want me to proceed now, say "Post it" (or provide the bot token/permissions) and I will execute the send operation.
```
</details>

**Agent B's Answer (agent2.1):**
- Concise MVP-first approach with clear prioritization
- 6-step implementation plan: Scope & MVP, Architecture, Real-time streaming, Voting, Security, UX polish
- Shorter, more actionable Discord message prepared but **not executed** during coordination
- Clear notation: "After you confirm the message, I will post it"
- Sprint plan with example estimates and risk mitigations

<details>
<summary><u>📄 Agent B (GPT-5-mini) - Answer (agent2.1) ✓ Selected as Winner</u></summary>

```
Planned actions (what I'll do and why)
- Read the linked GitHub issue and extract the motivation, proposed solution, mockups, and implementation suggestions. (Done.)
- Prepare a short, clear summary + concrete implementation next steps for the MassGen Testing Server general channel so the team can quickly pick up tasks and assign owners.
- After you confirm the message, I will post it to the provided guild/channel (you gave: guild ID 1417773298309136445, channel ID 1417773298837880906). I'm not sending it in this planning message per your instruction to allow review.

What I found (short summary of the issue)
- Title: "[FEATURE] Web UI for MassGen". The issue proposes building a browser-based Web UI to run, monitor, and visualize multi-agent coordination workflows (motivation: CLI is powerful but less accessible; UI helps demos, non-dev users, live visualization). Opened Oct 2, 2025.
- Proposed features: prompt input + config upload, Run button, live agent cards (logs/status/results), orchestrator summary, voting/comparison UI, visual timeline, export/download and different display modes. Mockups/prototype screenshots are attached to the issue.

Recommended implementation next steps (MVP-first, concrete tasks)
1) Scope & MVP (1–2 week sprint):
   - MVP features: Prompt input + config upload; Run button that triggers MassGen run; live agent cards showing logs/ statuses; basic voting view to compare final outputs; a minimal orchestrator summary panel. Keep styling minimal (Tailwind/vanilla CSS).
   - Acceptance criteria: able to run a demo_config.yaml from the UI, see live logs stream, and perform a vote between at least two agent outputs.
2) Architecture & tech choices (day 1):
   - Frontend: React (create-next-app or Vite) + Tailwind for quick styling. Keep components small (AgentCard, OrchestratorPanel, VotingPanel, Timeline).
   - Backend: small Node/Express or FastAPI service that exposes endpoints to trigger MassGen runs and stream logs. Wrap the existing MassGen CLI as a programmatic API (child_process spawn or a thin adapter) to avoid rewriting core. Use WebSockets or Server-Sent Events (SSE) to push logs/status to the UI.
   - Deployment: Dockerize backend and a static build for frontend; development via docker-compose.
3) Real-time streaming & reliability (sprint 2):
   - Implement WebSocket or SSE streaming from the backend that relays agent initialization, run progress, and final outputs to the UI.
   - Add reconnect/backoff logic and persisted run IDs so users can reconnect to live sessions.
4) Voting & comparison (sprint 2):
   - Structured comparison view: show each agent's reasoning side-by-side and allow highlighting differences; compute a simple score for each output (optional) and allow manual vote.
5) Security, access, and configs (sprint 1–2):
   - Limit who can trigger runs (auth via GitHub OAuth or a simple API token initially), validate uploaded config files (schema check), and sanitize prompts/outputs for display.
6) UX polish, export, and testing (sprint 3):
   - Add timeline view, download/export of results, copy-to-clipboard for outputs, small UX polish, and E2E tests for main flows.

Suggested owners, milestone, and estimates (example)
- Week 0 (planning): design final MVP UI and API contract (owner: frontend lead). 2–3 days.
- Sprint 1 (2 weeks): implement backend adapter + endpoints + minimal frontend to trigger runs + live logs (owner: backend dev + frontend dev). 2 weeks.
- Sprint 2 (2 weeks): voting view, reconnection/IDs, security (owner: full-stack). 2 weeks.
- Sprint 3 (1–2 weeks): polish, export, tests, docs, demo. 1–2 weeks.

Quick risks & mitigations
- Risk: Wrapping CLI could introduce stability issues in long-running sessions. Mitigation: Spawn processes with per-run IDs, log rotation, and health checks; gradually move critical logic into a stable API if needed.
- Risk: Real-time streaming scale. Mitigation: Start with SSE for simplicity and scale with a message broker (Redis Pub/Sub) if usage increases.

Proposed Discord message (ready to post)
----
Heads up — I reviewed the GitHub issue "[FEATURE] Web UI for MassGen" opened on Oct 2, 2025. Summary: the issue proposes building a browser-based Web UI (React/Next.js recommended) to make MassGen accessible to non-dev users and enable live visualization of multi-agent runs: prompt input, config upload, Run button, live agent cards (logs/status/results), orchestrator summary, voting/comparison view, and timeline. Mockups and implementation suggestions are attached to the issue.

Implementation next steps I propose:
1) Scope an MVP: prompt input + config upload, Run button, live agent cards, basic voting panel. (Target: 1–2 week sprint.)
2) Build a thin backend adapter that wraps the MassGen CLI and exposes endpoints; stream logs to the frontend via WebSockets or SSE. (Tech: Node/Express or FastAPI)
3) Sprint plan & owners: plan (2–3 days), sprint 1 (2 weeks) backend+frontend MVP, sprint 2 (2 weeks) voting+stability, sprint 3 (1–2 weeks) polish + docs.

Call to action:
- Volunteers: please reply with which part you want to own (frontend, backend adapter, WebSocket/SSE, security).
- If no objections I'll open a project board and propose PR templates + an initial branch to start the adapter.

Link to the GitHub issue for details: https://github.com/Leezekun/MassGen/issues/276
----

Notes about posting
- I will send the above message to the MassGen Testing Server general channel (guild ID 1417773298309136445, channel ID 1417773298837880906) once you confirm or request changes. The issue I referenced: opened Oct 2, 2025 with detailed mockups and implementation suggestions.

Next steps for me after your approval
- Post the message to the specified channel.
- Optionally create a GitHub-linked project board and open an initial tracking issue/PR if you want me to.

If you'd like changes, tell me what to add/remove in the Discord message (tone, length, or specific owners to call out) and I'll update it and send.
```
</details>

**Final Presentation (Agent B Execution):**
- Agent B **actually executed** the Discord tool during final presentation
- Message successfully posted to channel ID 1417773298837880906
- Slightly condensed version of planned message with bullet points
- Added structured formatting with Sprint plan breakdown
- Confirmed successful execution: "Message successfully sent to channel ID: 1417773298837880906"

<details>
<summary><u>🎤 Final Presentation (Agent B Execution - What Actually Happened)</u></summary>

```
Message posted to #general in the MassGen Testing Server (channel ID 1417773298837880906).

What I posted (copy):
- Heads up — I reviewed the GitHub issue "[FEATURE] Web UI for MassGen" (opened Oct 2, 2025). Summary: the issue proposes building a browser-based Web UI to make MassGen accessible to non-dev users and enable live visualization of multi-agent runs: prompt input, config upload, Run button, live agent cards (logs/status/results), orchestrator summary, voting/comparison view, and timeline. Mockups and implementation suggestions are attached to the issue.

- Implementation next steps I propose:
  1) Scope an MVP (1–2 week sprint): prompt input + config upload, Run button, live agent cards with streaming logs/status, and a basic voting panel for comparing outputs.
  2) Architecture & tech choices (day 1): Frontend in React (Next.js or Vite) + Tailwind; Backend adapter in Node/Express or FastAPI that wraps the MassGen CLI and exposes REST + WebSocket/SSE endpoints.
  3) Sprint plan (example):
     • Week 0 (2–3 days): finalize MVP UI and API contract.
     • Sprint 1 (2 weeks): backend adapter + frontend Run UI + live logs.
     • Sprint 2 (2 weeks): voting/comparison, reconnection/run IDs, basic auth.
     • Sprint 3 (1–2 weeks): polish, export, tests, docs, demo.
  4) Key tasks & owners (suggested): frontend skeleton + AgentCard/Voting (frontend); CLI adapter + streaming (backend); sample demo_config and tests (dev/test); Docker/CI (infra).
  5) Risks & mitigations: CLI wrapping stability → per-run processes and sandboxing; streaming scale → start SSE/WS and add Redis Pub/Sub if needed; auth → API tokens/GitHub OAuth initially.

- Call to action:
  - Volunteers: please reply with which area you can own (frontend, backend adapter, streaming, infra, testing) and any preferences on stack.
  - If no objections I'll create a project board and open initial skeleton PRs/branches to get started.

- Details & link: https://github.com/Leezekun/MassGen/issues/276

Next steps I can take now (choose one):
- Create the GitHub project board and initial tracking issues / PR skeletons.
- Open the initial skeleton PRs/branches for frontend and backend.
- Add the suggested sprint timeline to the project board and tag volunteers once they reply.

Tell me which of those to proceed with (or if you want wording changes) and I'll continue.
```

**MCP Tool Execution Evidence:**
```
🔧 MCP: 🔧 [MCP Tool] Calling mcp__discord__discord_send...
🔧 MCP: Arguments for Calling mcp__discord__discord_send: {"channelId":"1417773298837880906","message":"..."}
🔧 MCP: Results for Calling mcp__discord__discord_send: Message successfully sent to channel ID: 1417773298837880906
🔧 MCP: ✅ [MCP Tool] mcp__discord__discord_send completed
```
</details>


**Comparative Analysis:**

The three stages above reveal MassGen's planning mode in action:

**Agent A's Characteristics:**
- More comprehensive and detailed planning documentation
- Explicit execution phase separation ("When you want me to post...")
- Longer Discord message with specific timeline dates
- Structured with clear sections and subsections

**Agent B's Characteristics:**
- Concise, MVP-first approach with prioritization
- Action-oriented implementation steps
- Shorter, more digestible Discord message
- Risk analysis and mitigation strategies included

**Planning Mode Success:**
- **Both agents planned** Discord messages without execution during coordination
- **No duplicate messages** sent (planning mode prevented premature execution)
- **Clean voting** based on planned content quality, not execution side effects
- **Winner-only execution** in final presentation (Agent B)

**Why Agent B Was Selected:**
Agent B's answer achieved consensus through its concise, actionable approach. While both agents provided excellent planning, Agent B's MVP-first methodology, clear sprint breakdown, and risk mitigation strategies made it more immediately actionable. The shorter Discord message was also easier to digest while still covering all essential points.

**Key v0.0.29 validation**: Planning mode successfully prevented duplicate Discord messages during multi-agent coordination, allowing agents to collaborate on communication content before any external action occurred. Only the winner executed tools after consensus.

### Anything Else

**Planning Mode Effectiveness:**

The case study demonstrates planning mode's impact on collaboration quality:
- **3 total restarts** - efficient refinement without execution overhead
- **Clean coordination** - no duplicate messages or rollback complexity
- **Informed voting** - agents evaluated planned content, not execution results
- **Safe execution** - single message posted after consensus

This suggests:
1. Planning mode reduces coordination complexity by deferring execution
2. Agents can focus on content quality without worrying about side effects
3. Multi-agent collaboration becomes viable for communication tasks
4. External system safety is maintained throughout the process

**System Message Effectiveness:**

The system message's instruction was crucial:
```
Never duplicate actions, especially communications (messages, emails) or workspace modifications (file edits, Discord/Slack posts). For these critical operations, first provide the content as your answer, then execute the tools only during final presentation.
```

Combined with `enable_planning_mode`, this created a powerful safety mechanism where:
- Agents understood to plan rather than execute immediately
- Content was provided in answers for review and voting
- Tool execution happened only in final presentation phase

<h2 id="conclusion">🎯 Conclusion</h2>

The MCP Planning Mode in v0.0.29 successfully solves the external integration safety challenge that users faced when trying to use multi-agent collaboration with MCP tools. The key user benefits specifically enabled by this feature include:

1. **Safe Multi-Agent MCP Usage**: Users can now leverage multi-agent quality (debate, refinement, voting) with MCP tools (Discord, Twitter, Notion) without risking duplicate actions
2. **Consensus-Driven Execution**: External actions only occur after agents reach consensus, preventing premature or redundant operations
3. **Preserved Collaboration Benefits**: Full multi-agent collaboration maintained while adding execution safety

**Broader Implications:**

The planning mode represents a paradigm shift for MassGen's MCP integration:
- **Quality + Safety**: Users get both collaborative quality improvements AND external system safety
- **Applicable to All Communication Tools**: Concept extends to any MCP server involving external actions (messaging, notifications, API calls)

**What This Enables:**

With v0.0.29, users can now build multi-agent workflows that:
- Collaboratively draft and refine Discord/Slack/Teams messages before posting
- Work together on Twitter/social media content with single-message execution
- Coordinate on Notion/document updates with consensus-based writing
- Plan API calls and external integrations without premature execution

This case study validates that planning mode successfully bridges the gap between multi-agent quality and external integration safety, enabling new categories of collaborative workflows that were previously too risky to attempt.

---

<h3 id="status-tracker">📌 Status Tracker</h3>

- [✓] Planning phase completed
- [✓] Features implemented (v0.0.29)
- [✓] Testing completed
- [✓] Demo recorded (logs available)
- [✓] Results analyzed
- [✓] Case study reviewed

---

*Case study conducted: October 8, 2025*
*MassGen Version: v0.0.29*
*Configuration: massgen/configs/tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml*
