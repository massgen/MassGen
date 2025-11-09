# Filesystem-Based Tool Discovery Design

**Status**: Draft
**Author**: MassGen Team
**Date**: 2025-01-08
**Related Issues**: [#414](https://github.com/massgen/MassGen/issues/414), [#425](https://github.com/massgen/MassGen/issues/425), [#461](https://github.com/massgen/MassGen/issues/461), [#465](https://github.com/massgen/MassGen/issues/465)
**Related Links**: [Anthropic: Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp), [Apple: CodeAct](https://machinelearning.apple.com/research/codeact), [Cloudflare: Code Mode](https://blog.cloudflare.com/code-mode/)

## Overview

This design document proposes a paradigm shift in how MassGen agents discover and execute tools, moving from **context-based tool injection** to **filesystem-based tool discovery**. Instead of injecting all available MCP servers and custom tools into the agent's context window, we expose them as files in the agent's workspace filesystem, allowing agents to discover tools using powerful CLI primitives (ripgrep, ast-grep, potentially semtools) and execute them via code.

**Key Breakthrough**: With filesystem-first mode, users can **attach 100+ MCP servers** (hundreds of tools) without any context cost. Agents discover and load only the tools they need for each specific task. This enables a "universal workspace" configuration that works for any task, eliminating the need to manually predict and configure which MCPs are needed.

## Motivation

### Current Limitations

**Context Pollution**:
- MassGen currently injects 30+ tool schemas directly into agent context
- Each MCP server adds tool definitions to the prompt
- This consumes significant tokens (Anthropic reports ~150K tokens for comprehensive tool definitions)
- Smaller models struggle with large tool sets
- Irrelevant tools pollute context and may confuse decision-making

**Lack of Discoverability**:
- Users must manually select MCP servers in YAML config
- No dynamic tool discovery during execution
- Agents cannot adapt tool usage based on task evolution
- No mechanism to discover community MCP servers

**Inefficient Tool Usage**:
- Agents must make multiple tool calls for complex workflows
- No ability to compose tools programmatically
- Cannot save and reuse successful tool workflows
- Difficult to implement conditional logic or loops with tools

### Benefits of Filesystem-Based Approach

**Massive Context Savings** (Anthropic reports 98.7% reduction):
- Load only relevant tool definitions on-demand
- Typical reduction from ~150K tokens to ~2K tokens
- Enables using smaller, faster models effectively

**Progressive Disclosure**:
- Agents list available servers/tools as needed
- Read specific tool definitions only when required
- Natural discovery through filesystem navigation

**Unlimited MCP Server Availability** (NEW):
- **Attach hundreds of MCP servers** without context pollution
- Current limitation: ~5-10 MCP servers before context overflows
- With filesystem-first: **100+ MCP servers** with no context impact
- Agents discover and load only the relevant ones for each task
- Example: Attach every common MCP (GitHub, Google Drive, Slack, Salesforce, Notion, Linear, PostgreSQL, MongoDB, etc.) and let agents find what they need
- Enables "universal workspace" configuration that works for any task

**Code-Based Composition**:
- Write scripts that call multiple tools
- Use native control flow (loops, conditionals)
- Save successful workflows as reusable skills
- Filter and transform data in execution environment

**Unified Architecture**:
- MCP tools → files in `servers/`
- Custom tools → files in `tools/`
- Skills → files in `skills/`
- Memory → files in `memory/`
- Everything discoverable via same search primitives

## Architecture Design

### Filesystem Structure

The workspace uses a **shared + per-agent** structure to avoid duplication while maintaining agent isolation:

```
/massgen_workspace/           # Shared across all agents in a session
├── servers/                  # MCP server tools (read-only, SHARED)
│   ├── filesystem/
│   │   ├── read_file.py
│   │   ├── write_file.py
│   │   ├── list_directory.py
│   │   └── __init__.py
│   ├── google-drive/
│   │   ├── getDocument.py
│   │   ├── searchFiles.py
│   │   └── __init__.py
│   └── salesforce/
│       ├── updateRecord.py
│       └── __init__.py
├── tools/                    # MassGen custom tools (read-only, SHARED)
│   ├── web/
│   │   ├── playwright_navigate.py
│   │   ├── screenshot.py
│   │   └── __init__.py
│   └── multimodal/
│       ├── vision_understanding.py
│       └── __init__.py
├── skills/                   # Reusable workflows (read/write, SHARED)
│   ├── community/            # Shared skills from community or other agents
│   │   ├── create_website.py
│   │   └── analyze_codebase.py
│   └── agent_a/              # Agent-specific skills
│       └── my_workflow.py
└── agents/                   # Per-agent workspaces
    ├── agent_a/
    │   ├── workspace/        # Agent's working directory (temp_workspaces)
    │   ├── memory/           # Agent-specific memory (read/write)
    │   │   ├── core_memories.json
    │   │   ├── task_history.json
    │   │   └── learned_patterns.md
    │   └── tasks/            # Agent's task planning
    │       ├── current_task.yaml
    │       └── completed_tasks/
    └── agent_b/
        └── ...
```

**Sharing Strategy**:

- **`servers/` and `tools/`**: Single shared copy for all agents
  - Read-only to prevent conflicts
  - Generated once per session
  - Reduces disk usage and keeps tools consistent

- **`skills/`**: Hybrid approach
  - `skills/community/`: Shared skills all agents can use
  - `skills/{agent_id}/`: Agent-specific skills
  - Agents can promote their skills to community

- **`agents/{agent_id}/`**: Fully isolated per agent
  - `workspace/`: Maps to temp_workspaces/{agent_id}/
  - `memory/`: Agent's private memory
  - `tasks/`: Agent's task planning state

**Symlinking for Convenience**:

Each agent's execution environment has symlinks for easy access:

```
# Inside agent_a's code execution environment
/workspace/                   # Current working directory
├── servers -> /massgen_workspace/servers/      # Symlink to shared tools
├── tools -> /massgen_workspace/tools/          # Symlink to shared tools
├── skills -> /massgen_workspace/skills/        # Symlink to shared skills
├── memory -> /massgen_workspace/agents/agent_a/memory/  # Agent's memory
└── ... (agent's working files)
```

This allows agents to import tools naturally:
```python
from servers.filesystem import read_file  # Works from agent's perspective
from skills.community import create_website
```

**Benefits of This Structure**:
- **No duplication**: Tools generated once, shared by all agents
- **Isolation**: Agent memories and workspaces remain private
- **Skill sharing**: Agents can discover and use each other's successful workflows
- **Clear boundaries**: Read-only vs. read/write permissions prevent conflicts
- **Scalability**: Adding agents doesn't multiply tool storage

#### Sharing Model Details

**1. Tool Sharing (servers/ and tools/)**:

- **Generation**: Once per session, on first agent initialization
- **Storage**: Single location `/massgen_workspace/servers/` and `/massgen_workspace/tools/`
- **Access**: Read-only for all agents (enforced by filesystem permissions)
- **Updates**: If MCP servers are added/removed during session, regenerate tool files
- **Concurrency**: Multiple agents can read simultaneously (no locking needed)

**Example**: If 5 agents are running, they all read from the same `servers/google-drive/getDocument.py` file, avoiding 5x duplication.

**2. Skill Sharing (skills/)**:

Skills use a hybrid model:

```
/massgen_workspace/skills/
├── community/              # Shared across all agents (read/write)
│   ├── README.md          # Guidelines for contributing
│   ├── create_website.py
│   └── analyze_codebase.py
├── agent_a/               # Agent A's private skills (read/write by agent_a)
│   └── my_workflow.py
└── agent_b/               # Agent B's private skills (read/write by agent_b)
    └── experimental.py
```

**Skill Promotion Flow**:
1. Agent creates skill in their own directory: `skills/agent_a/my_workflow.py`
2. Agent tests and validates the skill
3. Agent can promote to community: copy to `skills/community/my_workflow.py`
4. Other agents discover via `rg "workflow" skills/community/` or `ls skills/community/`
5. Community skills can be reviewed/curated by users

**Access Control**:
- Agents can read all skills (their own + community)
- Agents can write only to their own directory and community directory
- User can manually curate community skills (delete low-quality ones)

**3. Memory Isolation (agents/{agent_id}/memory/)**:

Memory is strictly per-agent by default:

```python
# Agent A's perspective
with open("memory/core_memories.json") as f:  # Reads agent_a's memory
    my_memories = json.load(f)

# Agent A can optionally read Agent B's memory (if configured)
with open("/massgen_workspace/agents/agent_b/memory/learned_patterns.md") as f:
    other_memories = f.read()
```

**Configuration for Cross-Agent Memory Access**:

```yaml
agents:
  - id: "agent_a"
    memory:
      allow_read_from: ["agent_b", "agent_c"]  # Can read these agents' memories
      allow_write_to: []                       # Cannot write to others' memories

  - id: "agent_b"
    memory:
      allow_read_from: ["agent_a"]
      allow_write_to: []
```

**Use Cases**:
- **Isolated agents**: Default, each agent has private memory
- **Collaborative agents**: Agents can read each other's learned patterns
- **Supervisor-worker**: Supervisor reads all workers' memories to coordinate

**4. Workspace Isolation (agents/{agent_id}/workspace/)**:

Each agent's working directory is completely isolated:

```
/massgen_workspace/agents/
├── agent_a/
│   └── workspace/  -> /actual/path/to/temp_workspaces/agent_a/
│       ├── project_files/
│       ├── generated_code.py
│       └── output.txt
└── agent_b/
    └── workspace/  -> /actual/path/to/temp_workspaces/agent_b/
        └── (completely separate files)
```

- No sharing between agent workspaces
- Maps to existing `temp_workspaces/` directories
- Cleared when temp_workspaces are cleared
- Agent cannot access another agent's workspace files

**5. Shared vs. Per-Agent Summary**:

| Directory | Sharing Model | Access | Persistence |
|-----------|---------------|--------|-------------|
| `servers/` | **Shared** across all agents | Read-only | Session duration |
| `tools/` | **Shared** across all agents | Read-only | Session duration |
| `skills/community/` | **Shared** across all agents | Read/write | Persistent |
| `skills/{agent_id}/` | **Per-agent** | Read/write (own only) | Persistent |
| `agents/{agent_id}/memory/` | **Per-agent** (opt-in sharing) | Read/write (own), Read (others if allowed) | Persistent |
| `agents/{agent_id}/workspace/` | **Per-agent** (isolated) | Read/write (own only) | Temporary |

**Storage Efficiency**:

With 10 agents and 50 MCP tools + 30 custom tools:

- **Context-based approach**: 10 agents × 80 tool schemas in context = massive duplication
- **Filesystem-first (without sharing)**: 10 × 80 tool files = 800 files
- **Filesystem-first (with sharing)**: 1 × 80 tool files = 80 files ✅

Sharing reduces filesystem storage by 10x and keeps tool definitions consistent.

### MCP Tool Representation

Each MCP tool is represented as a Python file with:

1. **Typed interface** for inputs and outputs
2. **Docstring** describing the tool
3. **Implementation** that bridges to actual MCP call

Example: `servers/filesystem/read_file.py`

```python
"""Read contents of a file from the filesystem.

This tool reads the contents of a file and returns it as a string.
Supports text files up to 10MB in size.
"""

from typing import Optional
from dataclasses import dataclass

@dataclass
class ReadFileInput:
    """Input schema for read_file tool."""
    path: str  # Absolute or relative path to the file
    encoding: Optional[str] = "utf-8"  # File encoding

@dataclass
class ReadFileOutput:
    """Output schema for read_file tool."""
    content: str  # File contents
    size_bytes: int  # File size in bytes

async def read_file(path: str, encoding: str = "utf-8") -> ReadFileOutput:
    """Read a file from the filesystem.

    Args:
        path: Path to the file to read
        encoding: Character encoding (default: utf-8)

    Returns:
        ReadFileOutput with file contents and metadata

    Raises:
        FileNotFoundError: If the file doesn't exist
        PermissionError: If access is denied
    """
    # Implementation bridges to actual MCP server call
    from _massgen_runtime import call_mcp_tool

    result = await call_mcp_tool(
        server="filesystem",
        tool="read_file",
        arguments={"path": path, "encoding": encoding}
    )

    return ReadFileOutput(
        content=result["content"],
        size_bytes=len(result["content"].encode(encoding))
    )
```

**Key Design Decisions**:
- **Python over TypeScript**: MassGen uses Python primarily, agent code execution is Python-based
- **Dataclasses for schemas**: Type-safe, introspectable, familiar to Python developers
- **Bridge function**: `_massgen_runtime.call_mcp_tool()` handles actual MCP communication
- **Full docstrings**: Agents can read file to understand tool without loading into context

### Custom Tool Representation

Custom tools (MassGen's built-in tools) follow the same pattern but may directly implement functionality:

Example: `tools/web/playwright_navigate.py`

```python
"""Navigate to a URL using Playwright browser automation.

Opens a browser, navigates to the specified URL, and optionally
takes a screenshot. Useful for web scraping and testing.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class NavigateInput:
    url: str  # URL to navigate to
    screenshot: bool = False  # Whether to capture screenshot
    wait_for: Optional[str] = None  # CSS selector to wait for

@dataclass
class NavigateOutput:
    final_url: str  # Final URL after redirects
    title: str  # Page title
    screenshot_path: Optional[str] = None  # Path to screenshot if captured

async def navigate(
    url: str,
    screenshot: bool = False,
    wait_for: Optional[str] = None
) -> NavigateOutput:
    """Navigate to a URL using Playwright.

    Args:
        url: Target URL
        screenshot: Whether to capture screenshot
        wait_for: CSS selector to wait for before returning

    Returns:
        NavigateOutput with page information
    """
    # Direct implementation or bridge to existing tool system
    from massgen.tool._web_handlers._playwright import playwright_navigate

    result = await playwright_navigate(
        url=url,
        screenshot=screenshot,
        wait_for=wait_for
    )

    return NavigateOutput(
        final_url=result["final_url"],
        title=result["title"],
        screenshot_path=result.get("screenshot_path")
    )
```

### Runtime Bridge Architecture

The `_massgen_runtime` module provides the bridge between filesystem-based tool files and actual execution:

```python
# _massgen_runtime/__init__.py
"""MassGen runtime for code execution environment.

This module is automatically available in agent code execution contexts.
It provides bridges to MCP servers, custom tools, and system functions.
"""

from typing import Any, Dict
import asyncio

async def call_mcp_tool(
    server: str,
    tool: str,
    arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """Call an MCP tool on a connected server.

    Args:
        server: MCP server name (e.g., "filesystem", "google-drive")
        tool: Tool name (e.g., "read_file", "getDocument")
        arguments: Tool arguments as dictionary

    Returns:
        Tool execution result

    Raises:
        RuntimeError: If server is not connected
        ValueError: If tool doesn't exist or arguments are invalid
    """
    # Implementation connects to MassGen's MCP manager
    from massgen.mcp import get_active_mcp_manager

    manager = get_active_mcp_manager()
    return await manager.call_tool(server, tool, arguments)


async def call_custom_tool(
    tool_name: str,
    **kwargs: Any
) -> Any:
    """Call a MassGen custom tool.

    Args:
        tool_name: Fully qualified tool name (e.g., "web.playwright_navigate")
        **kwargs: Tool arguments

    Returns:
        Tool execution result
    """
    from massgen.tool import get_active_tool_manager

    manager = get_active_tool_manager()
    return await manager.execute_tool(tool_name, kwargs)


def save_skill(name: str, code: str, description: str) -> None:
    """Save a code snippet as a reusable skill.

    Args:
        name: Skill name (will be saved as skills/{name}.py)
        code: Python code for the skill
        description: Description for documentation
    """
    from pathlib import Path

    skills_dir = Path.cwd() / "skills"
    skills_dir.mkdir(exist_ok=True)

    skill_path = skills_dir / f"{name}.py"
    skill_path.write_text(f'"""{description}"""\n\n{code}')
```

### Tool Discovery Mechanism

Agents discover tools using standard CLI primitives and file operations:

**Basic Discovery (list available servers)**:
```python
import os

# List all available MCP servers
servers = os.listdir("servers/")
print(f"Available servers: {servers}")

# List tools in a specific server
filesystem_tools = os.listdir("servers/filesystem/")
print(f"Filesystem tools: {filesystem_tools}")
```

**Ripgrep for Keyword Search**:
```bash
# Find all tools related to "document"
rg "document" servers/ tools/ --type py -l

# Find tools with specific capabilities
rg "screenshot|image|visual" tools/ -i -l
```

**AST-grep for Structural Search**:
```bash
# Find all async functions (tools)
ast-grep --pattern 'async def $FUNC($$$)' servers/ tools/

# Find tools that return specific types
ast-grep --pattern 'def $FUNC($$$) -> $TYPE' servers/
```

**Reading Tool Documentation**:
```python
# Agents read the file to understand a tool
with open("servers/google-drive/getDocument.py") as f:
    doc = f.read()
    print(doc)  # Contains full docstring and type hints
```

**Semantic Search (Future/Optional)**:

For Phase 4, we can add semantic search capabilities using one of these options:

1. **Google File Search API** ([blog post](https://blog.google/technology/developers/file-search-gemini-api/))
   - Built-in semantic search for files
   - Integrates with Gemini API
   - Handles various file formats

2. **Semtools** ([GitHub](https://github.com/run-llama/semtools))
   - Open-source semantic search
   - PDF, DOCX, and code parsing
   - Local or cloud embeddings

3. **Custom embeddings** (via existing mem0ai/Qdrant)
   - Reuse MassGen's existing embedding infrastructure
   - Consistent with memory system

```python
from _massgen_runtime import semantic_search

# Find tools semantically related to a query
results = semantic_search(
    query="I need to download a PDF from Google Drive",
    search_paths=["servers/", "tools/"],
    top_k=5
)

for result in results:
    print(f"{result.path}: {result.relevance_score}")
```

**Decision**: Defer semantic search initially. Ripgrep and ast-grep are sufficient for MVP and avoid additional dependencies/costs. Evaluate semantic search once we have data on tool discovery patterns.

## Integration Points

### Skills (Issue #425)

Skills are saved workflows that agents can discover and reuse. When an agent successfully completes a complex task, they can save it as a skill:

```python
from _massgen_runtime import save_skill

# After successfully creating a website
save_skill(
    name="create_modern_website",
    code="""
import servers.filesystem as fs
import tools.web as web

async def create_website(project_name: str, style_reference: str):
    '''Create a modern website based on a style reference.'''
    # 1. Analyze reference website
    ref_page = await web.playwright_navigate(
        url=style_reference,
        screenshot=True
    )

    # 2. Generate HTML/CSS based on reference
    # ... (implementation)

    # 3. Write files to project directory
    await fs.write_file(
        path=f'{project_name}/index.html',
        content=html_content
    )

    return f'Website created at {project_name}/'
    """,
    description="Create a modern website by analyzing a reference site"
)
```

Other agents can then discover and use this skill:

```bash
# Agent searches for website creation skills
rg "create.*website" skills/ -i -l
```

```python
# Agent imports and uses the skill
from skills.create_modern_website import create_website

result = await create_website(
    project_name="my_project",
    style_reference="https://ag2.ai/"
)
```

### Memory (Issue #461)

Each agent gets a `memory/` directory for storing and retrieving memories. This is located at `/massgen_workspace/agents/{agent_id}/memory/` in the shared structure:

```
/massgen_workspace/agents/
├── agent_a/
│   ├── workspace/              # Maps to temp_workspaces/agent_a/
│   └── memory/                 # Agent's persistent memory
│       ├── core_memories.json      # Long-term facts
│       ├── task_history.json       # Previous tasks and outcomes
│       ├── learned_patterns.md     # Patterns the agent has learned
│       └── preferences.yaml        # User preferences
└── agent_b/
    └── memory/
        └── ...
```

**From Agent's Perspective**:
The `memory/` symlink points to their own memory directory:
```python
# Agent code sees memory/ as their own private storage
with open("memory/core_memories.json") as f:
    memories = json.load(f)
```

**Memory Operations**:

Agents can use ripgrep/ast-grep to search their own memories:

```bash
# Find all memories about a specific topic
rg "database optimization" memory/ -i

# Search structured memory files
ast-grep --pattern '{"topic": "performance", $$$}' memory/*.json
```

Agents can also read memories from other agents if configured (by accessing full path):

```python
import json

# Read another agent's learned patterns (if permitted)
with open("/massgen_workspace/agents/agent_b/memory/learned_patterns.md") as f:
    other_agent_patterns = f.read()

# Load own task history
with open("memory/task_history.json") as f:
    history = json.load(f)

# Find similar past tasks
similar_tasks = [
    task for task in history
    if "website" in task["description"].lower()
]
```

**Integration with temp_workspaces**:

- `workspace/` symlinks to existing `temp_workspaces/{agent_id}/` directory
- `memory/` is persistent across sessions (stored outside temp_workspaces)
- When temp_workspaces are cleared, memory persists
- Skills created by agents can reference memory for context

**Benefits**:
- Simpler than dedicated memory APIs
- Leverages same search primitives used for tools
- Human-readable formats (JSON, YAML, Markdown)
- Easy to inspect, backup, and version control
- Natural integration with code execution paradigm

### Filesystem-First MCP Mode (Issue #414)

Add a configuration option to enable filesystem-based tool discovery:

```yaml
# massgen/configs/filesystem_first_example.yaml
agents:
  - id: "agent_a"
    backend:
      type: "openai"
      model: "gpt-4o"

# Global MassGen configuration
massgen:
  execution_mode: "filesystem_first"  # New option (default: "context_based")

  # Tools that remain in-context for immediate access
  in_context_tools:
    # Core filesystem operations (required for basic functionality)
    filesystem:
      - read_file
      - write_file
      - list_directory
      - create_directory
      - move_file
      - get_file_info

    # Code execution (if available)
    code_execution:
      - execute_python
      - execute_bash

    # Optional: Can be customized per config
    # essential_custom_tools:
    #   - search_memory  # If agent needs frequent memory access

  # All other MCPs exposed as files (not in context)
  # With filesystem-first, you can attach HUNDREDS of MCPs!
  # Agents will discover and load only what they need.
  available_mcp_servers:
    # Productivity & Communication
    - google-drive
    - gmail
    - google-calendar
    - slack
    - discord
    - notion
    - confluence

    # Development & Code
    - github
    - gitlab
    - linear
    - jira

    # Databases
    - postgres
    - mysql
    - mongodb
    - redis
    - elasticsearch

    # Sales & CRM
    - salesforce
    - hubspot
    - stripe

    # Cloud & Infrastructure
    - aws
    - gcp
    - azure
    - docker
    - kubernetes

    # ... (add as many as you want, no context cost!)

  # Custom tools exposed as files (not in context)
  available_custom_tools:
    - web.playwright_navigate
    - web.screenshot
    - multimodal.vision_understanding
    - multimodal.video_analysis
    # ... (30+ other tools)

  # Enable CLI search tools in Docker
  search_tools:
    enable_ripgrep: true
    enable_ast_grep: true
    enable_semtools: false  # Optional, defer initially
```

#### What Stays in Context (Essential Tools)

**Criteria for "Essential"**:
A tool is essential if it meets ANY of these criteria:
1. **Required for code execution**: Needed to read/write code and execute it
2. **High frequency usage**: Used in >80% of agent tasks
3. **Low token cost**: Tool schema is small (<500 tokens)
4. **Bootstrap dependency**: Needed to discover/use other tools

**Default Essential Tools**:

1. **Filesystem Operations** (6-8 tools, ~2K tokens):
   - `read_file`: Read source code and tool definitions
   - `write_file`: Save generated code and results
   - `list_directory`: Discover available tools/skills
   - `create_directory`: Organize workspace
   - `move_file`: Manage files
   - `get_file_info`: Check file metadata

   **Why essential**: Code execution paradigm requires file I/O. Agents need these to read tool definitions from `servers/` and `tools/` directories.

2. **Code Execution** (2 tools, ~1K tokens):
   - `execute_python`: Run Python code (primary execution model)
   - `execute_bash`: Run shell commands (for ripgrep, ast-grep, etc.)

   **Why essential**: Core to filesystem-first paradigm. Agents write code to compose tools rather than chaining tool calls.

3. **Total Context Cost**: ~3-4K tokens (vs. ~150K for all tools)
   - **Reduction**: 97-98% context savings
   - Leaves room for task description, conversation history, and code

**What Goes to Filesystem** (Not in Context):

1. **Specialized MCP Servers** (ALL tools as files):
   - google-drive, salesforce, github, slack, postgres, etc.
   - Agent discovers via `ls servers/` or `rg "keyword" servers/`
   - Reads tool definition only when needed

2. **MassGen Custom Tools** (ALL tools as files):
   - Web scraping (playwright, screenshot)
   - Multimodal (vision, video analysis)
   - Data processing, API calls, etc.
   - Reduces context from ~30 tool schemas to 0

3. **Future/Rare Tools**: Tools agents might never use for a given task

#### Configuration Behavior

**IMPORTANT REQUIREMENT**: Filesystem-first mode **REQUIRES** code execution to be enabled. Without code execution, agents cannot:
- Read tool definition files from `servers/` and `tools/`
- Run ripgrep/ast-grep for tool discovery
- Write code to compose and call tools
- Execute the generated tool-calling scripts

**Recommended Setup**: Enable Docker-based code execution for isolation and security:

```yaml
massgen:
  execution_mode: "filesystem_first"

  # Code execution is REQUIRED for filesystem_first mode
  code_execution:
    enabled: true
    mode: "docker"  # Strongly recommended for security
    docker:
      image: "massgen/filesystem-first:latest"  # Pre-configured with ripgrep, ast-grep
      network: "host"  # Allows access to MCP servers
```

If code execution is not available, MassGen should:
1. **Refuse to start** in filesystem_first mode
2. **Suggest fallback** to `execution_mode: "context_based"`
3. **Provide clear error** explaining the requirement

When `execution_mode: "filesystem_first"`:
1. ✅ **REQUIRES** code execution (Docker strongly recommended)
2. ✅ Essential filesystem + code execution tools injected into context
3. ✅ All other MCPs represented as files in `servers/`
4. ✅ All custom tools represented as files in `tools/`
5. ✅ Docker container includes ripgrep, ast-grep
6. ✅ Agents use code execution to discover and call non-essential tools
7. ✅ Shared workspace structure (see "Filesystem Structure" section)

**Customization Options**:

```yaml
# Advanced: Override default essential tools
massgen:
  execution_mode: "filesystem_first"

  in_context_tools:
    # Minimal set (even more context reduction)
    filesystem: [read_file, write_file, list_directory]
    code_execution: [execute_python]

  # OR: Add domain-specific essentials
  in_context_tools:
    filesystem: "*"  # All filesystem tools
    code_execution: "*"
    web: [playwright_navigate]  # If web-focused agent
```

**Backward Compatibility**:

```yaml
# Default mode (existing behavior)
massgen:
  execution_mode: "context_based"  # All tools in context
```

### Docker Container Setup

**CRITICAL**: Filesystem-first mode requires Docker-based code execution. The paradigm depends on agents being able to:
- Execute Python code to read tool files
- Run bash commands (ripgrep, ast-grep)
- Import and call tools from `servers/` and `tools/`

**Without Docker code execution**: Agents cannot discover or use non-essential tools, making filesystem-first mode non-functional.

The code execution Docker container needs additional tools:

**Dockerfile additions**:
```dockerfile
# Base image with Python
FROM python:3.11-slim

# Install search tools (REQUIRED for filesystem-first mode)
RUN apt-get update && apt-get install -y \
    ripgrep \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Rust and ast-grep (REQUIRED for structural code search)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
RUN cargo install ast-grep --locked

# Optional: Install semtools (Phase 4, defer initially)
# RUN pip install semtools

# Install MassGen dependencies
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

# Copy MassGen runtime module (provides MCP/tool bridges)
COPY massgen/_massgen_runtime /workspace/_massgen_runtime

# Generate tool files on container startup
COPY scripts/generate_tool_files.py /scripts/
RUN python /scripts/generate_tool_files.py
```

**Pre-populate workspace**:
When starting a session with `filesystem_first` mode:
1. Generate Python files for all available MCP servers
2. Generate Python files for all custom tools
3. Create shared directory structure (`servers/`, `tools/`, `skills/`, `memory/`)
4. Initialize agent-specific memory directories
5. Create symlinks in each agent's workspace
6. Add `_massgen_runtime` to Python path
7. Validate ripgrep and ast-grep are available

## Implementation Phases

### Phase 1: Core Infrastructure (2-3 weeks)

**Goal**: Basic filesystem representation and discovery

**Tasks**:
1. Create `_massgen_runtime` module with MCP/tool bridges
2. Implement tool file generator (MCP schemas → Python files)
3. Add `execution_mode` configuration option
4. Update Docker container with ripgrep and ast-grep
5. Modify workspace initialization for filesystem-first mode

**Deliverables**:
- Agents can list and read tool files
- Basic MCP tool execution via `_massgen_runtime.call_mcp_tool()`
- Example config demonstrating filesystem-first mode
- Unit tests for runtime bridges

**Success Criteria**:
- Agent can discover and call MCP tools from filesystem
- Token usage reduced by >80% compared to context-based approach
- All existing functionality still works in traditional mode

### Phase 2: Skills System (1-2 weeks)

**Goal**: Enable saving and reusing code workflows

**Tasks**:
1. Implement `save_skill()` runtime function
2. Create `skills/` directory structure
3. Add skill discovery documentation for agents
4. Build skill validation and testing framework
5. Create example skills library

**Deliverables**:
- Agents can save successful workflows as skills
- Skills are discoverable via search primitives
- Skills can be imported and reused
- Community can share skills

**Success Criteria**:
- Agent completes task, saves as skill, reuses in different context
- Skills are properly documented with docstrings
- Skills can be shared between agents

### Phase 3: Filesystem Memory Integration (1-2 weeks)

**Goal**: Replace or augment mem0ai with filesystem-based memory

**Tasks**:
1. Design memory file formats (JSON, YAML, Markdown)
2. Create per-agent memory directories
3. Implement memory read/write operations
4. Add memory search examples to documentation
5. Build memory migration tool (mem0ai → filesystem)

**Deliverables**:
- Each agent has persistent memory directory
- Memories are searchable with ripgrep/ast-grep
- Clear patterns for structured vs. unstructured memory
- Migration path from existing memory system

**Success Criteria**:
- Agent stores and retrieves memories from filesystem
- Memory search is fast and accurate
- Can optionally use both filesystem and mem0ai simultaneously

### Phase 4: Advanced Search (Future)

**Goal**: Add semantic search capabilities (optional)

**Tasks**:
1. **Evaluate semantic search options**:
   - [Google File Search API](https://blog.google/technology/developers/file-search-gemini-api/) - Built-in with Gemini
   - [Semtools](https://github.com/run-llama/semtools) - Open-source, multi-format parsing
   - Local embeddings via mem0ai/Qdrant - Reuse existing infrastructure
2. Implement semantic search runtime function
3. Add configuration for embedding models
4. Benchmark search quality and performance
5. Document when to use semantic vs. keyword search

**Deliverables**:
- Optional semantic search for tools/skills/memory
- Configuration options for embedding backends (Google/semtools/local)
- Performance benchmarks vs. ripgrep
- Best practices guide
- Cost analysis for API-based vs. local embeddings

**Success Criteria**:
- Semantic search finds relevant tools >90% of the time
- Performance acceptable for interactive use (<1s for typical queries)
- Clear guidance on when semantic search adds value over ripgrep/ast-grep
- Cost-effective for typical usage patterns

**Note**: Defer this phase until we have data on tool discovery patterns. Ripgrep and ast-grep may be sufficient for most use cases.

## Open Questions and Design Decisions

### 1. MCP Tool File Generation

**Question**: How do we generate Python files from MCP tool schemas?

**Proposed Solution**:
- Parse MCP server tool schemas (JSON Schema)
- Generate Python dataclasses for inputs/outputs
- Generate function signature from schema
- Extract description from schema for docstring
- Create bridge call to `_massgen_runtime.call_mcp_tool()`

**Example Generation**:
```python
# Input: MCP tool schema
{
  "name": "read_file",
  "description": "Read a file from the filesystem",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "File path"},
      "encoding": {"type": "string", "default": "utf-8"}
    },
    "required": ["path"]
  }
}

# Output: Generated Python file
# (see example in MCP Tool Representation section)
```

**Challenges**:
- Complex nested schemas
- Union types and optional fields
- Streaming responses
- Binary data handling

**Decision Needed**: Should we generate files once on config load or dynamically on demand?
- **Option A**: Pre-generate all files when session starts (simpler, faster discovery)
- **Option B**: Generate on-demand when agent accesses a server (lazy, saves disk space)
- **Recommendation**: Option A for MVP, Option B as optimization

### 2. Custom Tool Representation

**Question**: Should custom tools be represented as files or just exposed directly?

**Considerations**:
- **Pro File Representation**: Consistent with MCP tools, searchable, saves context
- **Con File Representation**: Duplication of code, sync issues if tool changes

**Proposed Approach**:
- **Essential tools** (filesystem, terminal): Keep in context
- **Specialized tools** (web scraping, vision, etc.): Represent as files
- **All tools**: Available as files for discovery/documentation even if also in-context

**Decision Needed**: How to handle tool updates during session?
- Regenerate files when tool registry changes?
- Accept staleness for session duration?
- **Recommendation**: Regenerate on session start, accept staleness during session

### 3. Security and Sandboxing

**Question**: How do we prevent agents from accessing tools they shouldn't?

**Considerations**:
- In context-based approach, we control which tools are injected
- In filesystem approach, all tools are visible (but might not be executable)

**Proposed Solution**:
- **Visibility**: All available tools are visible as files (for discovery)
- **Execution**: `_massgen_runtime` enforces access control
- **Bridge layer** checks agent permissions before calling MCP/tools
- Configuration specifies allowed servers/tools per agent

**Example**:
```python
# Agent tries to call unauthorized tool
result = await call_mcp_tool("admin-panel", "delete_all_users", {})

# Runtime raises PermissionError
# PermissionError: Agent 'agent_a' not authorized for server 'admin-panel'
```

**Decision Needed**: Should unauthorized tools be hidden from filesystem or visible but not callable?
- **Option A**: Hide completely (cleaner, but agents can't discover what exists)
- **Option B**: Visible but fail on execution (transparent, enables discovery)
- **Recommendation**: Option B - transparency aids debugging and tool requests

### 4. Language Choice: Python vs. TypeScript

**Question**: Anthropic's examples use TypeScript. Should we use Python or support both?

**Analysis**:
- **MassGen codebase**: Primarily Python
- **Agent code execution**: Python (Jupyter kernels)
- **Community**: Python dominates AI/ML ecosystem
- **Type safety**: Python 3.10+ has excellent typing support
- **Familiarity**: Our users expect Python

**Proposed Decision**: Use Python for MVP
- Dataclasses for schemas (similar to TypeScript interfaces)
- Type hints for all function signatures
- Could support TypeScript in future if demand exists

**Trade-offs**:
- TypeScript has better type safety (compile-time checks)
- Python is more familiar to target audience
- **Recommendation**: Python for MVP, TypeScript as future enhancement

### 5. Performance and Caching

**Question**: Will file reads be slower than in-context tools?

**Analysis**:
- **File read overhead**: ~1ms per tool file read
- **Context overhead**: ~100ms+ for 30 tool schemas in context
- **Trade-off**: Slight latency per tool vs. massive context reduction

**Proposed Optimizations**:
1. **Cache tool file contents** in memory after first read
2. **Lazy generation**: Only generate files for servers agent uses
3. **Index file**: Create `servers/index.json` listing all tools with summaries
4. **Smart prefetching**: Predict likely tools based on task and prefetch

**Decision Needed**: Is caching worth the complexity for MVP?
- **Recommendation**: No caching in MVP, measure performance, add if needed

### 6. Backward Compatibility

**Question**: How do we maintain backward compatibility with existing configs?

**Proposed Approach**:
- Default `execution_mode: "context_based"` (current behavior)
- Opt-in `execution_mode: "filesystem_first"` for new paradigm
- Support both modes simultaneously
- Gradual migration path for users

**Migration Strategy**:
1. Release filesystem-first as experimental feature
2. Gather feedback and iterate
3. Eventually make filesystem-first the default
4. Deprecate context-based mode in future version

### 7. Tool Updates and Versioning

**Question**: What happens when an MCP server updates its tools?

**Scenarios**:
1. **During session**: Tool schemas change mid-execution
2. **Between sessions**: Tools added/removed/modified
3. **Version conflicts**: Different agents need different tool versions

**Proposed Solution**:
- **During session**: Keep static tool files (accept staleness)
- **Between sessions**: Regenerate all tool files on session start
- **Versioning**: Include version in tool files, validate compatibility

**Example version tracking**:
```python
# servers/google-drive/__version__.py
__version__ = "1.2.3"
__mcp_server__ = "google-drive"
__last_generated__ = "2025-01-08T10:30:00Z"
```

## Success Metrics

How will we measure if this paradigm shift is successful?

### Quantitative Metrics

1. **Context Reduction**: Aim for >90% reduction in tool-related tokens
   - Baseline: ~150K tokens for comprehensive tool definitions
   - Target: <15K tokens with filesystem-first approach

2. **MCP Server Scalability**: Number of MCP servers agents can effectively use
   - Baseline (context-based): 5-10 MCP servers before context overflow
   - Target (filesystem-first): **100+ MCP servers** with no context degradation
   - Metric: Successfully complete tasks with 50+ available MCP servers

3. **Cost Savings**: Measure cost per task completion
   - Expected savings: ~50-70% due to context reduction

4. **Task Completion Rate**: Should maintain or improve
   - Current: ~85% success rate on standard benchmarks
   - Target: ≥85% with filesystem-first

5. **Performance**: Time to complete tasks
   - Additional file read overhead should be minimal (<5% slower)
   - Code-based composition may enable faster complex workflows (>20% faster)

6. **Tool Discovery Accuracy**: How often agents find the right tools
   - Target: >95% accuracy with ripgrep/ast-grep alone
   - Measure: Agent selects correct MCP server for task from 50+ options

### Qualitative Metrics

1. **Developer Experience**: Survey users on ease of use
   - Is tool discovery intuitive?
   - Is code-based composition easier than tool chaining?
   - Do skills provide value?

2. **Community Adoption**: Track skills sharing
   - Number of skills created
   - Number of skills reused
   - Community contributions

3. **Flexibility**: Can agents solve more complex tasks?
   - Ability to compose multi-step workflows
   - Adaptation to novel tool combinations
   - Self-improvement through skill creation

## Use Case: Universal Workspace Configuration

One of the most powerful capabilities enabled by filesystem-first mode is the **"Universal Workspace"** - a single configuration that works for any task.

### Current Approach (Context-Based) - Limited MCP Servers

```yaml
# massgen/configs/limited_workspace.yaml
massgen:
  execution_mode: "context_based"

agents:
  - id: "agent"
    backend:
      type: "openai"
      model: "gpt-4o"
      mcp_servers:
        # Can only attach 5-10 before context overflows
        - filesystem
        - github
        - google-drive
        - slack
        - postgres
        # Adding more would exceed context limits!
```

**Problem**: User must predict which MCPs they'll need:
- Building a website? Need playwright, github, vercel
- Analyzing sales data? Need salesforce, postgres, stripe
- Research task? Need google-drive, notion, arxiv

Users must **manually switch configurations** for different tasks or risk context overflow.

### Filesystem-First Approach - Unlimited MCPs

```yaml
# massgen/configs/universal_workspace.yaml
massgen:
  execution_mode: "filesystem_first"
  code_execution:
    enabled: true
    mode: "docker"

agents:
  - id: "universal_agent"
    backend:
      type: "openai"
      model: "gpt-4o"
      # NO mcp_servers here - all defined globally!

# Global: Attach EVERY MCP you might ever need
# Total: 50+ MCP servers, 200+ tools, 0 context cost
available_mcp_servers:
  # Productivity (12 servers)
  - google-drive
  - gmail
  - google-calendar
  - google-docs
  - notion
  - confluence
  - slack
  - discord
  - teams
  - zoom
  - dropbox
  - box

  # Development (15 servers)
  - github
  - gitlab
  - bitbucket
  - linear
  - jira
  - asana
  - trello
  - jenkins
  - circleci
  - vercel
  - netlify
  - heroku
  - aws
  - gcp
  - azure

  # Databases (8 servers)
  - postgres
  - mysql
  - mongodb
  - redis
  - elasticsearch
  - neo4j
  - dynamodb
  - cassandra

  # Sales & Business (10 servers)
  - salesforce
  - hubspot
  - stripe
  - shopify
  - quickbooks
  - zendesk
  - intercom
  - mailchimp
  - sendgrid
  - twilio

  # Research & Data (7 servers)
  - arxiv
  - pubmed
  - wikipedia
  - wolfram
  - kaggle
  - youtube
  - twitter

  # ... and MORE as needed!
```

**Agent Task Flow**:

```bash
# User: "Analyze our Q4 sales and send a summary to the team"

# Agent discovers relevant tools:
$ rg "sales|revenue|crm" servers/ -i -l
servers/salesforce/query_records.py
servers/stripe/list_charges.py
servers/hubspot/get_deals.py

$ rg "send|message|post" servers/ -i -l
servers/slack/post_message.py
servers/teams/send_notification.py

# Agent reads only the needed tools (2 out of 200+)
$ cat servers/salesforce/query_records.py
$ cat servers/slack/post_message.py

# Agent writes code using discovered tools
from servers.salesforce import query_records
from servers.slack import post_message

q4_data = await query_records(
    query="SELECT Amount FROM Opportunity WHERE CloseDate >= 2024-10-01"
)
# ... analysis ...
await post_message(channel="#sales", text=summary)
```

**Benefits**:
- ✅ **One config for all tasks**: No need to predict or switch configs
- ✅ **Zero context cost**: 50+ servers = same context as 0 servers
- ✅ **Agent discovers**: Finds right tools automatically via search
- ✅ **Loads only needed**: Reads 2-3 tool definitions, ignores the rest
- ✅ **Future-proof**: Add new MCPs without affecting existing tasks

**Comparison**:

| Metric | Context-Based | Filesystem-First |
|--------|---------------|------------------|
| Max MCP servers | 5-10 | **100+** |
| Context per server | ~15K tokens | ~0 tokens |
| Total context cost | 75K-150K | **~3K tokens** |
| Config management | Different config per task | **One universal config** |
| Tool discovery | Manual selection | **Automatic via search** |
| Scalability | Limited by context | **Unlimited** |

This enables a **"load once, use forever"** model where users set up their workspace once with all possible integrations, and agents intelligently discover what they need.

## Alternative Approaches Considered

### Alternative 1: Hybrid Approach

**Description**: Keep essential tools in context, expose others as files

**Pros**:
- Preserves fast access to common tools
- Gradual migration path

**Cons**:
- Inconsistent interface (some tools in context, some as files)
- Agents need to learn two paradigms

**Decision**: Implement as migration strategy, not final state

### Alternative 2: Dedicated Tool Discovery Agent

**Description**: One agent specializes in tool discovery, recommends to others

**Pros**:
- Centralizes tool knowledge
- Could use advanced semantic search

**Cons**:
- Adds latency (extra agent call)
- Single point of failure
- Doesn't reduce context for main agents

**Decision**: Could combine with filesystem approach for advanced discovery

### Alternative 3: Dynamic Context Loading

**Description**: Automatically detect needed tools and inject into context

**Pros**:
- No file system representation needed
- Maintains current architecture

**Cons**:
- Still consumes context window
- Adds complexity of prediction
- Doesn't enable code composition

**Decision**: Not viable for context reduction goals

## Next Steps

1. **Review this design doc** with team and stakeholders
2. **Prototype Phase 1** with minimal MCP server (filesystem only)
3. **Benchmark** context reduction and performance
4. **Iterate** on tool file format based on agent behavior
5. **Document** agent best practices for tool discovery
6. **Expand** to full MCP server support
7. **Build** skills system and community sharing

## References

### Core Paradigm
- [Anthropic: Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Apple: CodeAct - Executable Code Actions for Agent Learning](https://machinelearning.apple.com/research/codeact)
- [Cloudflare: Code Mode](https://blog.cloudflare.com/code-mode/)

### Tool Discovery & Context Engineering
- [Contextual.ai: Context Engineering for MCP](https://contextual.ai/blog/context-engineering-for-your-mcp-client)

### Skills & Memory
- [Anthropic Skills Repository](https://github.com/anthropics/skills)
- [Letta: Agent Memory](https://www.letta.com/blog/agent-memory)

### Semantic Search (Future)
- [Google: File Search with Gemini API](https://blog.google/technology/developers/file-search-gemini-api/)
- [Semtools Repository](https://github.com/run-llama/semtools)

## Appendix: Example Agent Workflow

Here's an end-to-end example of how an agent would work in filesystem-first mode:

**Task**: "Create a modern website for my project by analyzing a reference site"

**Agent Workflow**:

1. **Discover available tools**:
```bash
# Agent runs in code execution
import os
print(os.listdir("servers/"))  # ['filesystem', 'google-drive', ...]
print(os.listdir("tools/"))    # ['web', 'multimodal', ...]
```

2. **Search for relevant tools**:
```bash
# Use ripgrep to find web-related tools
!rg "navigate|browser|webpage" tools/ servers/ -i -l
```

Output:
```
tools/web/playwright_navigate.py
tools/web/screenshot.py
```

3. **Read tool documentation**:
```python
with open("tools/web/playwright_navigate.py") as f:
    print(f.read())
```

4. **Use the tool**:
```python
from tools.web import playwright_navigate

# Navigate to reference site
ref_result = await playwright_navigate(
    url="https://ag2.ai/",
    screenshot=True,
    wait_for="main"
)

print(f"Reference site title: {ref_result.title}")
print(f"Screenshot saved: {ref_result.screenshot_path}")
```

5. **Analyze and generate**:
```python
from tools.multimodal import vision_understanding

# Understand the reference design
analysis = await vision_understanding(
    image_path=ref_result.screenshot_path,
    prompt="Describe the design elements, color scheme, and layout of this website"
)

# Generate HTML/CSS based on analysis
html_content = generate_html(analysis)  # Agent writes this function
css_content = generate_css(analysis)
```

6. **Write files**:
```python
from servers.filesystem import write_file

await write_file("my_project/index.html", html_content)
await write_file("my_project/styles.css", css_content)
```

7. **Save as skill**:
```python
from _massgen_runtime import save_skill

save_skill(
    name="create_website_from_reference",
    code=current_code,  # Agent's working code
    description="Create a website by analyzing a reference site's design"
)
```

**Benefits demonstrated**:
- Agent discovered tools without them being in context
- Composed multiple tools with code (navigate → screenshot → analyze → generate → write)
- Saved successful workflow as reusable skill
- Next agent can discover and reuse this skill
