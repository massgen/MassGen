# Filesystem Tools & Safety

**Introduced in:** v0.0.16 (September 2025)
**Enhanced in:** v0.0.21, v0.0.22, v0.0.25, v0.0.26, v0.0.29

MassGen provides comprehensive filesystem capabilities with built-in safety features to prevent accidental data loss and ensure secure multi-agent collaboration. This guide covers workspace isolation, permission systems, and all filesystem operations.

## Release History

| Version | Date | What Changed |
|---------|------|-------------|
| v0.0.16 | Sept 8, 2025 | **Unified Filesystem Support** - FilesystemManager class, MCP-based operations for Gemini and Claude Code |
| v0.0.21 | Sept 19, 2025 | **Advanced Permissions** - PathPermissionManager, context paths with READ/WRITE permissions, function hooks |
| v0.0.22 | Sept 22, 2025 | **Workspace Copy Tools** - MCP-based file copying, enhanced file operations |
| v0.0.25 | Sept 29, 2025 | **Multi-Turn Support** - Persistent filesystem context across conversation rounds, session management |
| v0.0.26 | Oct 1, 2025 | **Enhanced Operations** - File deletion tools, file-based context paths, protected paths, workspace cleanup |
| v0.0.29 | Oct 8, 2025 | **File Operation Tracker** - Read-before-delete enforcement, agent-created file tracking, enhanced safety |

## Overview

MassGen's filesystem architecture provides:

- **Workspace Isolation** - Each agent has its own working directory
- **Context Paths** - Controlled access to specific files/directories
- **Protected Paths** - Read-only files within writable directories
- **Permission System** - Fine-grained read/write control
- **File Operation Tracker** - Read-before-delete enforcement (v0.0.29)
- **Multi-turn Sessions** - Persistent filesystem state across conversation rounds

## Workspace Isolation

Each agent operates in its own isolated workspace, preventing accidental interference between agents.

### Basic Workspace Configuration

```yaml
agents:
  - id: "agent1"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      cwd: "workspace1"  # Agent 1's working directory

  - id: "agent2"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      cwd: "workspace2"  # Agent 2's working directory

orchestrator:
  snapshot_storage: "snapshots"              # Workspace snapshots
  agent_temporary_workspace: "temp_workspaces"  # Temporary workspaces
```

**Example Config**: [`gemini_mcp_filesystem_test.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test.yaml)

### How Workspaces Work

1. **Coordination Phase**: Agents work in temporary workspaces
2. **Final Presentation**: Winning agent's workspace is used for final output
3. **Snapshots**: Workspace states are saved between coordination rounds

**Workspace Structure:**
```
project/
├── workspace1/              # Agent 1's workspace
│   ├── file1.txt
│   └── subdir/
├── workspace2/              # Agent 2's workspace
│   ├── file2.txt
│   └── subdir/
├── temp_workspaces/         # Temporary workspaces during coordination
│   ├── agent1_round1/
│   └── agent2_round1/
└── snapshots/               # Workspace snapshots
    ├── round1_agent1.tar.gz
    └── round1_agent2.tar.gz
```

## Context Paths

Context paths provide agents with controlled access to specific files or directories outside their workspace.

**Key Features:**
- **Flexible Paths**: Use absolute paths (`/home/user/project`) or relative paths (`.`, `src/`, `../data`)
- **Permission Control**: `read` or `write` (write permissions apply only to final agent)
- **Multi-Agent Access**: All agents can access context paths, but write access is restricted during coordination

### Basic Context Path

```yaml
orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"

  context_paths:
    - path: "."  # Current directory (relative path)
      permission: "write"
    - path: "/home/user/project/data"  # Absolute path
      permission: "read"
```

**What Happens:**
- All agents can access files in the specified paths
- During coordination: **read-only** access (all agents, regardless of permission setting)
- During final presentation: **write** access granted only if `permission: "write"` is set

**Example Config**: [`fs_permissions_test.yaml`](../../massgen/configs/tools/filesystem/fs_permissions_test.yaml)

### Permission Levels

```yaml
context_paths:
  - path: "reference_docs/"  # Can be absolute or relative
    permission: "read"       # Always read-only

  - path: "."                # Current directory
    permission: "write"      # Read during coordination, write for final agent only
    protected_paths:         # Optional: files immune from modification
      - ".env"
      - "config.json"
```

**Permission Behavior:**

| Phase | `permission: "read"` | `permission: "write"` |
|-------|---------------------|----------------------|
| Coordination (all agents) | Read-only | Read-only |
| Final Presentation (winning agent only) | Read-only | Read & Write |

**Important:** Write permissions only apply to the **final agent** during the presentation phase, ensuring your files are protected during multi-agent coordination.

### File-Level Context Path

Provide access to a single file without exposing the entire directory:

```yaml
context_paths:
  - path: "massgen/configs/resources/v0.0.21-example/styles.css"
    permission: "write"
```

**Result:**
- ✅ `styles.css` is accessible
- ❌ `index.html` (sibling file) is **NOT** accessible
- ❌ Parent directory contents are hidden

**Example Config**: [`gemini_gpt5nano_file_context_path.yaml`](../../massgen/configs/tools/filesystem/gemini_gpt5nano_file_context_path.yaml)

**Use Cases:**
- Provide specific reference files without exposing entire codebase
- Limit agents to modifying specific configuration files
- Prevent accidental changes to unrelated files

## Protected Paths

Protected paths allow you to mark specific files as read-only within a writable context path.

### Configuration

```yaml
context_paths:
  - path: "massgen/configs/resources/v0.0.21-example"
    permission: "write"
    protected_paths:
      - "index.html"  # This file is read-only (protected)
      # styles.css remains writable
```

**Result:**
- ✅ `styles.css` → Can modify/delete
- ❌ `index.html` → Read-only (protected)

**Example Config**: [`gemini_gpt5nano_protected_paths.yaml`](../../massgen/configs/tools/filesystem/gemini_gpt5nano_protected_paths.yaml)

### Use Cases

**Reference Files:**
```yaml
context_paths:
  - path: "project/"
    permission: "write"
    protected_paths:
      - "REQUIREMENTS.md"  # Don't modify requirements
      - "LICENSE"          # Don't modify license
```

**Template Preservation:**
```yaml
context_paths:
  - path: "templates/"
    permission: "write"
    protected_paths:
      - "base_template.html"  # Protect template, allow modifications to copies
```

## File Operation Tracker (v0.0.29)

The File Operation Tracker enforces read-before-delete policies to prevent accidental data loss.

### Read-Before-Delete Enforcement

**Rule:** Agents must read a file before deleting it (unless they created the file).

**How It Works:**

```python
# Scenario 1: Agent reads then deletes (ALLOWED)
agent.read_file("data.txt")      # Agent reads the file
agent.delete_file("data.txt")    # Deletion allowed ✅

# Scenario 2: Agent deletes without reading (BLOCKED)
agent.delete_file("data.txt")    # Deletion blocked ❌
# Error: "Cannot delete file: agent has not read this file yet"

# Scenario 3: Agent-created files (ALLOWED)
agent.write_file("new.txt", "content")  # Agent creates file
agent.delete_file("new.txt")            # Deletion allowed ✅
```

### Why Read-Before-Delete?

**Prevents:**
- Blind deletion of important files
- Accidental removal of files the agent hasn't examined
- Loss of data without agent understanding content

**Encourages:**
- Deliberate file operations
- Agent awareness of filesystem state
- Safer multi-agent collaboration

### Exemptions

Files created by the agent are exempt from read-before-delete:

```python
# Agent creates a file
agent.write_file("temp_analysis.txt", "...")

# Can delete immediately (agent created it)
agent.delete_file("temp_analysis.txt")  # ✅ Allowed
```

## Deletion Tools

MassGen provides tools for safe file deletion with validation.

### Single File Deletion

```python
delete_file(path, recursive=False)
```

**Example:**
```yaml
# Agent workflow
1. read_file("old_file.txt")        # Read first
2. delete_file("old_file.txt")      # Then delete
```

**Validation:**
- ✅ Agent has read the file OR created it
- ✅ Path is within permitted directories
- ✅ File is not in protected_paths
- ❌ Otherwise deletion is blocked

### Batch Deletion

```python
delete_files_batch(
  base_path="project/",
  include_patterns=["*.tmp", "*.log"],
  exclude_patterns=["important.log"]
)
```

**Use Case - Workspace Cleanup:**

```yaml
# Config: gemini_gemini_workspace_cleanup.yaml
context_paths:
  - path: "massgen/configs/resources/v0.0.26-example"
    permission: "write"
```

**Agent Workflow:**
1. Analyze messy directory with multiple HTML files
2. Identify which files to keep
3. Use `delete_files_batch` to remove redundant files
4. Clean workspace contains only essential files

**Example Config**: [`gemini_gemini_workspace_cleanup.yaml`](../../massgen/configs/tools/filesystem/gemini_gemini_workspace_cleanup.yaml)

## Multi-Turn Sessions

Multi-turn sessions enable persistent filesystem state across multiple conversation rounds.

### Configuration

```yaml
orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"
  session_storage: "sessions"  # Enable multi-turn sessions
```

**Example Config**: [`two_gemini_flash_filesystem_multiturn.yaml`](../../massgen/configs/tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn.yaml)

### How Multi-Turn Works

**Round 1:**
```bash
uv run python -m massgen.cli \
  --config multiturn_config.yaml \
  "Create a Python project structure"

# Creates: src/, tests/, README.md
# Session saved to: sessions/session_abc123/
```

**Round 2 (same session):**
```bash
uv run python -m massgen.cli \
  --config multiturn_config.yaml \
  --session-id session_abc123 \
  "Add unit tests to the project"

# Agents see existing structure from Round 1
# Add: tests/test_*.py files
```

**Round 3:**
```bash
uv run python -m massgen.cli \
  --config multiturn_config.yaml \
  --session-id session_abc123 \
  "Add documentation"

# Agents see all previous work
# Add: docs/ directory and files
```

### Use Cases

**Iterative Development:**
- Round 1: Create basic structure
- Round 2: Add features
- Round 3: Add tests
- Round 4: Add documentation

**Collaborative Refinement:**
- Round 1: Multiple agents propose approaches
- Round 2: Refine winning approach
- Round 3: Polish and optimize

### Available Multi-Turn Configs

- [`two_gemini_flash_filesystem_multiturn.yaml`](../../massgen/configs/tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn.yaml) - 2 Gemini agents
- [`grok4_gpt5_gemini_filesystem_multiturn.yaml`](../../massgen/configs/tools/filesystem/multiturn/grok4_gpt5_gemini_filesystem_multiturn.yaml) - 3 agents (Grok-4, GPT-5, Gemini)
- [`grok4_gpt5_claude_code_filesystem_multiturn.yaml`](../../massgen/configs/tools/filesystem/multiturn/grok4_gpt5_claude_code_filesystem_multiturn.yaml) - 3 agents with Claude Code
- [`two_claude_code_filesystem_multiturn.yaml`](../../massgen/configs/tools/filesystem/multiturn/two_claude_code_filesystem_multiturn.yaml) - 2 Claude Code agents

## Backend-Specific Filesystem Tools

### Claude Code

Claude Code provides native filesystem tools:

```yaml
agent:
  id: "claude_code_agent"
  backend:
    type: "claude_code"
    cwd: "workspace"
    permission_mode: "bypassPermissions"  # or "strict"

    # Native tools
    allowed_tools:
      - "Read"       # Read files
      - "Write"      # Write files
      - "Edit"       # Edit existing files
      - "MultiEdit"  # Multiple edits in one operation
      - "Bash"       # Execute shell commands
      - "Grep"       # Search within files
      - "Glob"       # Find files by pattern
      - "LS"         # List directory contents
```

**Native Tools:**
- `Read` - Read file contents
- `Write` - Create or overwrite files
- `Edit` - Make targeted edits to existing files
- `MultiEdit` - Multiple edits in single operation
- `Bash` - Execute shell commands
- `Grep` - Search file contents
- `Glob` - Find files by pattern
- `LS` - List directory contents
- `TodoWrite` - Task management
- `NotebookEdit` - Jupyter notebook editing

**Example Configs:**
- [`claude_code_single.yaml`](../../massgen/configs/tools/filesystem/claude_code_single.yaml) - Single Claude Code agent
- [`claude_code_context_sharing.yaml`](../../massgen/configs/tools/filesystem/claude_code_context_sharing.yaml) - Multiple Claude Code agents

### Gemini

Gemini has **native filesystem MCP support** - no MCP server installation needed:

```yaml
agent:
  id: "gemini_agent"
  backend:
    type: "gemini"
    model: "gemini-2.5-pro"
    cwd: "workspace"  # Automatic filesystem access
```

**Features:**
- Built-in file operations
- No external dependencies
- Works out of the box

**Example Configs:**
- [`gemini_mcp_filesystem_test.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test.yaml) - Dual Gemini agents
- [`gemini_mcp_filesystem_test_single_agent.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test_single_agent.yaml) - Single agent

## Permission System Architecture

### Permission Hierarchy

```
1. Workspace (cwd)           → Full access within workspace
2. Context Paths             → Controlled access to specific paths
3. Protected Paths           → Read-only files within context paths
4. File Operation Tracker    → Read-before-delete enforcement
```

### Permission Resolution

**Example Configuration:**
```yaml
agents:
  - id: "agent1"
    backend:
      cwd: "workspace1"

orchestrator:
  context_paths:
    - path: "project/"
      permission: "write"
      protected_paths:
        - "README.md"
```

**Access Control:**

| Path | Coordination | Final Presentation |
|------|-------------|-------------------|
| `workspace1/file.txt` | Read & Write | Read & Write |
| `project/code.py` | Read-only | Read & Write |
| `project/README.md` | Read-only | Read-only (protected) |
| `other/file.txt` | No access | No access |

### PathPermissionManager

The `PathPermissionManager` handles all permission checks:

**Features:**
- Validates all file operations
- Enforces context path permissions
- Checks protected paths
- Integrates with FileOperationTracker
- Tracks read/write/delete operations

**Methods:**
```python
# Permission checking
can_read(agent_id, path)
can_write(agent_id, path)
can_delete(agent_id, path)

# Operation tracking
track_read_operation(agent_id, path)
track_write_operation(agent_id, path)
track_delete_operation(agent_id, path)
```

## Complete Configuration Example

```yaml
agents:
  - id: "architect"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      cwd: "architect_workspace"

  - id: "developer"
    backend:
      type: "openai"
      model: "gpt-5"
      cwd: "developer_workspace"

orchestrator:
  # Workspace management
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"
  session_storage: "sessions"

  # Context paths with permissions
  context_paths:
    # Writable project directory
    - path: "project/"
      permission: "write"
      protected_paths:
        - "README.md"      # Protected reference
        - "LICENSE"        # Protected license
        - "requirements.txt"  # Protected dependencies

    # Read-only reference documentation
    - path: "docs/reference/"
      permission: "read"

    # Single file access
    - path: "config/app_config.yaml"
      permission: "write"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

## Common Patterns

### Pattern 1: Code Review & Modification

```yaml
context_paths:
  - path: "src/"
    permission: "write"
    protected_paths:
      - "src/main.py"  # Protect entry point
```

**Workflow:**
1. Agents review all code (read access)
2. Agents propose changes to utility files
3. Entry point (`main.py`) remains unchanged

### Pattern 2: Template-Based Generation

```yaml
context_paths:
  - path: "templates/"
    permission: "write"
    protected_paths:
      - "base.html"
      - "layout.html"
```

**Workflow:**
1. Agents read templates
2. Agents create new pages based on templates
3. Original templates remain pristine

### Pattern 3: Iterative Development

```yaml
orchestrator:
  session_storage: "sessions"

context_paths:
  - path: "project/"
    permission: "write"
```

**Workflow:**
1. **Round 1**: Create structure → `sessions/session_123/`
2. **Round 2**: Add features (builds on Round 1)
3. **Round 3**: Add tests (builds on Round 2)
4. **Round 4**: Documentation (complete project)

### Pattern 4: Workspace Cleanup

```yaml
context_paths:
  - path: "messy_project/"
    permission: "write"
```

**Workflow:**
1. Agents analyze directory
2. Identify redundant files
3. Use `delete_files_batch` to clean up
4. Result: Clean, organized workspace

## Safety Best Practices

### 1. Use Protected Paths for Critical Files

```yaml
protected_paths:
  - "database_config.yaml"
  - "production_secrets.env"
  - "LICENSE"
```

### 2. Start with Read-Only, Escalate if Needed

```yaml
# Start conservative
- path: "codebase/"
  permission: "read"

# Escalate only if modifications needed
- path: "specific_file.py"
  permission: "write"
```

### 3. Use File-Level Context for Precision

```yaml
# Instead of exposing entire directory
- path: "config/"
  permission: "write"

# Expose only specific file
- path: "config/app_settings.yaml"
  permission: "write"
```

### 4. Leverage File Operation Tracker

No configuration needed - automatic read-before-delete enforcement prevents accidental data loss.

### 5. Use Multi-Turn for Complex Tasks

```yaml
session_storage: "sessions"
```

Build complexity incrementally across rounds instead of one large operation.

## Troubleshooting

### Permission Denied Errors

**Problem:** `PermissionError: Cannot write to path`

**Solutions:**
- Check path is in `context_paths` with `permission: "write"`
- Verify path is not in `protected_paths`
- Ensure operation is during final presentation (not coordination) for write access

### Read-Before-Delete Blocked

**Problem:** `Cannot delete file: agent has not read this file yet`

**Solutions:**
- Have agent read the file first: `read_file(path)` then `delete_file(path)`
- Or write the file first (agent-created files are exempt)

### Context Path Not Accessible

**Problem:** Agent can't access files in context path

**Solutions:**
- Verify `path` is correct and exists
- Check path doesn't have typos
- Ensure path is absolute or relative (relative paths are resolved from current working directory)
- For current directory, use `"."` instead of leaving blank

### Protected Path Modification Attempted

**Problem:** `Cannot modify protected file`

**Solutions:**
- Intended behavior - protected paths are read-only
- Remove from `protected_paths` if modification needed
- Or create copy and modify the copy

## All Filesystem Configurations

**Browse:** [`massgen/configs/tools/filesystem/`](../../massgen/configs/tools/filesystem/)

**Examples:**
- **Basic**: [`claude_code_single.yaml`](../../massgen/configs/tools/filesystem/claude_code_single.yaml)
- **Context Paths**: [`fs_permissions_test.yaml`](../../massgen/configs/tools/filesystem/fs_permissions_test.yaml)
- **Protected Paths**: [`gemini_gpt5nano_protected_paths.yaml`](../../massgen/configs/tools/filesystem/gemini_gpt5nano_protected_paths.yaml)
- **File-Level Access**: [`gemini_gpt5nano_file_context_path.yaml`](../../massgen/configs/tools/filesystem/gemini_gpt5nano_file_context_path.yaml)
- **Workspace Cleanup**: [`gemini_gemini_workspace_cleanup.yaml`](../../massgen/configs/tools/filesystem/gemini_gemini_workspace_cleanup.yaml)
- **Multi-Turn**: [`multiturn/`](../../massgen/configs/tools/filesystem/multiturn/) - 4 configs

## Next Steps

- [Backend Support](./backend-support.md) - Filesystem capabilities by backend
- [MCP Integration](./mcp-integration.md) - Gemini native filesystem MCP
- [Planning Mode](./planning-mode.md) - Safe filesystem operations with planning
- [Configuration Guide](./configuration-guide.md) - Setting up filesystem configs
- [Safety Features](./safety-features.md) - Additional safety mechanisms (Coming Soon)

## Additional Release Information

- **Workspace Isolation**: Available since v0.0.16 (September 2025)
- **Context Paths**: v0.0.21+ (September 2025)
- **Protected Paths**: v0.0.26+ (October 2025)
- **File Operation Tracker**: v0.0.29 (October 2025)
- **Multi-Turn Sessions**: v0.0.25+ (September 2025)

---

**Last Updated:** October 2025 | **MassGen Version:** v0.0.29+
