# MassGen v0.0.15: Gemini MCP Notion Integration

MassGen v0.0.15 introduces the Model Context Protocol (MCP) integration for Gemini agents, enabling seamless access to external tools and services. This case study demonstrates the first implementation of MCP in MassGen through a practical learning content generation task using Notion API.

## Table of Contents
- [Prerequisites for MCP Integration](#prerequisites-for-mcp-integration)
- [📋 PLANNING PHASE](#planning-phase)
  - [📝 Evaluation Design](#evaluation-design)
    - [Prompt](#prompt)
    - [Baseline Config](#baseline-config)
    - [Baseline Command](#baseline-command)
    - [Expected Result](#expected-result)
  - [🔧 Evaluation Analysis](#evaluation-analysis)
    - [Current Failure Modes](#current-failure-modes)
    - [Success Criteria](#success-criteria)
  - [🎯 Desired Features](#desired-features)
- [🚀 TESTING PHASE](#testing-phase)
  - [📦 Implementation Details](#implementation-details)
    - [Version](#version)
    - [New Config](#new-config)
    - [Command](#command)
  - [🤖 Agents](#agents)
  - [🎥 Demo](#demo)
- [📊 EVALUATION & ANALYSIS](#evaluation-analysis)
  - [Results](#results)
    - [🔧 External Tool Integration - The Core Transformation](#external-tool-integration)
    - [🎯 Enhanced Task Completion](#enhanced-task-completion)
    - [🗳️ Voting Evolution](#voting-evolution)
- [🎯 Conclusion](#conclusion)
- [📌 Status Tracker](#status-tracker)


## Prerequisites for MCP Integration
  ### For Local MCP Servers (stdio):
  - **Runtime Environment**: Install the required runtime for your MCP server
    - [Node.js](https://nodejs.org/) for npm-based servers (e.g., `@notionhq/notion-mcp-server`)
    - Python for Python-based servers
    - Go for Go-based servers
  - **API Credentials**: Configure via environment variables (`NOTION_TOKEN`, `DISCORD_TOKEN`, etc.)

  ### For Remote MCP Servers (streamable-http):
  - **No local runtime needed** - servers run remotely
  - **Authentication**: Provide credentials via HTTP headers or secret management systems

  ### For All Deployments:
  - **MassGen Configuration**: Add `mcp_servers` section to your agent's backend configuration (see [Configuration File
  Format](../../README.md#configuration-file-format))

  **For general MCP setup in MassGen architecture:**
  - **[MCP Tools Overview & Setup Guide](../../massgen/mcp_tools/README.md)** - Complete guide to configuring MCP servers, tool discovery, security
  settings, and troubleshooting within MassGen
---

<h1 id="planning-phase">📋 PLANNING PHASE</h1>

<h2 id="evaluation-design">📝 Evaluation Design</h2>

### Prompt
"Generate and refine a structured Todo list for learning about LLM multi-agent systems, complete with exciting objectives and fun activities. Each time you have a new version, create a new Notion page with a title and the current date and time (including hours, minutes, seconds, and milliseconds) to store the list. Then, verify that you can access the page and read back the content. Create this page as a subpage under an existing notion page called 'LLM Agent Research (x)', where x is either 1 or 2 depending on which you have access to."

### Baseline Config
Prior to v0.0.15, Gemini agents would use a standard multi-agent configuration like `massgen/configs/two_agents_gemini.yaml` without any MCP server configuration.

### Baseline Command
```bash
uv run python -m massgen.cli --config massgen/configs/two_agents_gemini.yaml "Generate and refine a structured Todo list for learning about LLM multi-agent systems, complete with exciting objectives and fun activities. Each time you have a new version, create a new Notion page with a title and the current date and time (including hours, minutes, seconds, and milliseconds) to store the list. Then, verify that you can access the page and read back the content. Create this page as a subpage under an existing notion page called 'LLM Agent Research (x)', where x is either 1 or 2 depending on which you have access to."
```

### Expected Result 
Agents would generate excellent todo list content but would be unable to create Notion pages, store the content, or verify the results. They would likely provide instructions for manual copy-pasting to Notion instead.

<h2 id="evaluation-analysis">🔧 Evaluation Analysis</h2>

### Current Failure Modes
Before v0.0.15, MassGen's Gemini integration had notable limitations:

1. **No External Tool Access**: Gemini agents could only use built-in capabilities (web search, code execution)
2. **Limited Workflow Integration**: No way to interact with productivity tools like Notion, Slack, or databases
3. **Manual Output Management**: Users had to manually copy/paste agent outputs to external systems
4. **Isolated Agent Operations**: Agents couldn't persist data or share information through external systems

### Success Criteria
The new MCP integration would be considered successful if:

1. **External API Integration**: Agents can successfully create, read, and modify external resources (Notion pages) via MCP
2. **Multi-Agent Coordination**: Multiple agents can work with the same external system without conflicts
3. **Data Persistence**: Agent outputs are recorded in external systems
4. **End-to-End Validation**: Agents can verify final results match intended outcomes (beyond just API success)

<h2 id="desired-features">🎯 Desired Features</h2>

1. **MCP Client Integration**: A complete MCP client implementation for Gemini backend
2. **Automatic Tool Discovery**: Agents discover available MCP tools without manual configuration
3. **Session Management**: Maintained connections to MCP servers during agent execution
4. **Multi-Server Support**: Ability to connect to multiple MCP servers simultaneously
5. **Security Framework**: Safe execution of external tools with validation and sanitization
6. **Error Handling**: Robust error recovery for network issues and tool failures

---

<h1 id="testing-phase">🚀 TESTING PHASE</h1>

<h2 id="implementation-details">📦 Implementation Details</h2>

### Version
MassGen v0.0.15 (September 5, 2025)

### New Config
Configuration file: [`massgen/configs/gemini_notion_mcp.yaml`](../../massgen/configs/gemini_notion_mcp.yaml)

Key MCP configuration:
```yaml
mcp_servers:
  notionApi:
    type: "stdio"
    command: "npx"
    args: ["-y", "@notionhq/notion-mcp-server"]
    env:
      NOTION_TOKEN: "${NOTION_TOKEN_ONE}"
```

### Command
```bash
uv run python -m massgen.cli --config massgen/configs/gemini_notion_mcp.yaml "Generate and refine a structured Todo list for learning about LLM multi-agent systems, complete with exciting objectives and fun activities. Each time you have a new version, create a new Notion page with a title and the current date and time (including hours, minutes, seconds, and milliseconds) to store the list. Then, verify that you can access the page and read back the content. Create this page as a subpage under an existing notion page called 'LLM Agent Research (x)', where x is either 1 or 2 depending on which you have access to."
```

<h2 id="agents">🤖 Agents</h2>

- **Agent 1 (gemini-2.5-pro1)**: Primary content creator with access to Notion workspace "LLM Agent Research (1)" via NOTION_TOKEN_ONE
- **Agent 2 (gemini-2.5-pro2)**: Secondary content creator with access to Notion workspace "LLM Agent Research (2)" via NOTION_TOKEN_TWO

Both agents use Gemini 2.5 Pro model with:
- Web search enabled in configuration (no web calls observed in this run)
- MCP tool access via Notion API
- 19 available Notion MCP tools including API-post-search, API-post-page, API-patch-block-children

<h2 id="demo">🎥 Demo</h2>

[![MassGen v0.0.15 MCP Integration Demo](https://img.youtube.com/vi/Mg091VCBn90/0.jpg)](https://youtu.be/Mg091VCBn90)

---

<h1 id="evaluation-analysis">📊 EVALUATION & ANALYSIS</h1>

## Results

<h3 id="external-tool-integration">🔧 External Tool Integration - The Core Transformation</h3>

A key change is that MassGen agents can now **interact with external systems** through standardized protocols:

**Evidence from logs:**
- **19 MCP tools automatically discovered** per agent upon connection
- **Successful API calls**: `API-post-search` → `API-post-page` → `API-patch-block-children` → `API-get-block-children`
- **Real artifacts created**: Actual Notion pages with URLs that persist beyond the MassGen session
- **Read-back verification by both agents**: `API-get-block-children` called by Agent 1 (≈14:12:30–14:12:43) and Agent 2 (≈14:12:37–14:12:43) to confirm content accessibility.
```
🔧 MCP: ✅ MCP Tool Response from API-post-page: 
{"object":"page","id":"26480a06-b67b-81b4-b5a5-dbbf472df2cc",...}
```

<h3 id="enhanced-task-completion">🎯 Enhanced Task Completion</h3>

**Before**: "I can't create Notion pages, but here's a todo list you can copy-paste"
**After**: "I have successfully created and verified a new Notion page with your Todo list... Here is the verified Todo list from the Notion page"

The agents now:
1. **Complete the full requested workflow** including external system interactions
2. **Provide URLs to persistent results** rather than ephemeral text

<h3 id="voting-evolution">🗳️ Voting Evolution</h3>

Agents now vote on **execution success** not just content quality. From the logs:
> "Agent 1 provided a more comprehensive and well-structured Todo list that better addresses the user's request AND successfully fulfilled all aspects including creating a correctly titled Notion page"

<h2 id="conclusion">🎯 Conclusion</h2>

The MCP integration in v0.0.15 marks a significant step from isolated AI agents to connected, tool-enabled systems. Key improvements include:

1. **MCP Protocol Integration**: Agents have ability to connect to any MCP-compatible server (demonstrated with Notion)
2. **Workflow Integration**: integration with productivity tools
3. **Persistent Output**: Agent work is automatically preserved in external systems

**Broader Implications**: This positions MassGen as a platform for building AI agents that can interact with real-world systems, opening possibilities for:
- Database management agents
- CRM automation
- Cloud resource management
- Project management workflows
- API integration and testing

The success of this case study supports the MCP integration approach and demonstrates clear value for users requiring AI agents that can interact with external systems.

---

<h3 id="status-tracker">📌 Status Tracker</h3>
- ✅ Planning phase completed
- ✅ Features implemented  
- ✅ Testing completed
- ✅ Demo recorded
- ✅ Results analyzed
- ✅ Case study reviewed