# MassGen Permissions System and Context Files

This document explains MassGen's filesystem permissions system, context file management, and how to implement support in new backends.

## Overview

MassGen implements a sophisticated permissions system that allows agents to access user-specified files and directories with granular permission control. The system distinguishes between different types of paths and applies appropriate permissions based on the agent's role in the workflow.

## Architecture

### Core Components

1. **PathPermissionManager**: Central permission validation engine
2. **FilesystemManager**: High-level filesystem operations and workspace management
3. **Backend Integration**: Permission enforcement through hooks or MCP servers
4. **Context Paths**: User-specified files/directories with explicit permissions

### Permission Enforcement Strategies

MassGen uses different permission enforcement strategies based on backend capabilities:

- **Function-based backends** (OpenAI, Claude Code): Use `FunctionHookManager` with pre-call hooks
- **Session-based backends** (Gemini): Use `PermissionClientSession` to wrap MCP sessions
- **MCP backends** (Claude): Use MCP server hooks for permission validation

## Path Types and Permissions

### 1. Workspace Paths (`cwd`)
- **Purpose**: Primary working directory for agent operations
- **Permission**: Always `WRITE` - agents can create, modify, and delete files
- **Scope**: Agent-specific, isolated from other agents
- **Example**: `agent_workspace/`, `claude_code_workspace/`

### 2. Temporary Workspace Paths
- **Purpose**: Shared workspace for context sharing between agents
- **Permission**: Always `READ` - agents can read but not modify
- **Scope**: Contains snapshots from other agents for context
- **Example**: `temp_workspaces/agent1/`, `temp_workspaces/agent2/`

### 3. Context Paths (User-specified)
- **Purpose**: User-defined files/directories for agent access, e.g., for working in an existing repository
- **Permission**: Configurable `READ` or `WRITE` per path
- **Behavior**:
  - **Coordination agents**: Always `READ` regardless of YAML configuration
  - **Final agent**: Respects YAML configuration (`READ` or `WRITE`)
    - For now, we assume only one context path can have `WRITE` access to avoid complexity -- this represents the case of a single project directory being modified as is default in other CLI tools. We allow multiple write paths, but have no guarantee of performance.
    - The default behavior will be for the final agent to copy files from its workspace to the context path write directory at the end of the run, mimicking what would happen if we edited the files directly.
- **Example**: Project source files, documentation, configuration files

## Configuration

### YAML Configuration Example

```yaml
agents:
  - id: "context_agent"
    backend:
      type: "claude_code"
      model: "claude-sonnet-4-20250514"
      cwd: "workspace1"                      # Agent-specific workspace

  - id: "final_agent"
    backend:
      type: "openai"
      model: "gpt-5"
      cwd: "workspace2"                      # Agent-specific workspace

orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"
  # Context paths applied to all agents with permission control
  context_paths:
    - path: "/home/user/project/src"
      permission: "write"                    # Final agent can modify, context agents read-only
    - path: "/home/user/project/docs"
      permission: "read"                     # All agents get read-only access
    - path: "/home/user/shared_data"
      permission: "write"                    # Final agent can modify, context agents read-only
```

### Configuration Parameters

**Agent Level:**
- `cwd`: Agent's primary workspace directory (agent-specific isolation)
  - Automatically relocated to `.massgen/workspaces/` for clean project organization

**Orchestrator Level:**
- `context_paths`: List of user-specified paths with permissions applied to all agents
  - `path`: Absolute path to **file or directory** (both are supported)
  - `permission`: "read" or "write" - determines final agent access (context agents always read-only)
  - `protected_paths`: Optional list of paths within a context path that are immune from modification/deletion
  - **Default permission**: "write" when added interactively
  - **File context paths**: When a file is specified, only that file is accessible (sibling files are blocked)
- `snapshot_storage`: Directory for storing agent workspace snapshots
  - Automatically relocated to `.massgen/snapshots/`
- `agent_temporary_workspace`: Parent directory for temporary workspaces
  - Automatically relocated to `.massgen/temp_workspaces/`

**Permission Behavior:**
- **Context agents**: Always get READ access to context paths regardless of permission setting
- **Final agent**: Gets the configured permission (READ or WRITE) for context paths
- **Workspace (`cwd`)**: Always WRITE access for the owning agent

### Interactive Context Path Management

When running MassGen in **interactive mode** with filesystem support enabled (at least one agent has `cwd` configured), you'll be prompted to add the current directory as a context path:

```
📂 Context Paths:
   No context paths configured

❓ Add current directory as context path?
   /home/user/project
   [Y]es (default) / [P]rotected / [N]o / [C]ustom path:
```

**Features:**
- **Default behavior**: Pressing Enter adds current directory with **write** permission
- **Protected paths**: Enter 'p' to add current directory with protected paths (files/dirs immune from modification)
- **Custom paths**: Enter 'c' to specify a different file or directory (supports both absolute and relative paths)
- **Auto-detection**: Only shows when filesystem is enabled (agents have `cwd` configured)
- **Smart defaults**: Default permission is "write" for both current directory and custom paths
- **File support**: Can add individual files as context paths - only that file is accessible, siblings are blocked

**Example interaction:**
```bash
cd /home/user/my-project
massgen --config config.yaml

# Prompt appears:
❓ Add current directory as context path?
   /home/user/my-project
   [Y]es (default) / [N]o / [C]ustom path: [Enter]

✓ Added /home/user/my-project (write)
```

This eliminates the need to manually edit YAML config files for context paths.

### Using MassGen in Any Directory

MassGen is designed to work seamlessly from any directory without manual configuration changes. Here's how to use it effectively:

#### Quick Start: Directory-Based Workflow

```bash
# Navigate to your project
cd /home/user/my-project

# Run MassGen in interactive mode
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml

# You'll be prompted to add the current directory as a context path
❓ Add current directory as context path?
   /home/user/my-project
   [Y]es (default) / [N]o / [C]ustom path: [Enter]

✓ Added /home/user/my-project (write)

# Now agents can access and modify files in your project!
```

#### Single-Command Usage

```bash
# Run a single task in any directory
cd /path/to/project
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml "Add error handling to the authentication module"
```

#### How It Works

1. **Config Resolution**: MassGen automatically finds config files:
   - First checks the exact path you provide
   - Falls back to searching in the package's `configs/` directory
   - Works from any directory on your system

2. **Environment Variables**: `.env` files are loaded from multiple locations (priority order):
   - MassGen package `.env` (development fallback)
   - User home `~/.massgen/.env` (global user config)
   - Current directory `.env` (highest priority)

3. **Path Management**: All paths are automatically organized under `.massgen/`:
   - `cwd` paths → `.massgen/workspaces/`
   - `snapshot_storage` → `.massgen/snapshots/`
   - `agent_temporary_workspace` → `.massgen/temp_workspaces/`

4. **Context Paths**: In interactive mode with filesystem enabled, you're prompted to add the current directory

#### Installation for Global Access

Install MassGen using `uv tool` for isolated, global access:

```bash
# Clone the repository
git clone https://github.com/Leezekun/MassGen.git
cd MassGen

# Install MassGen as a global tool in editable mode
uv tool install -e .

# Now run from any directory
cd ~/projects/website
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml

cd ~/documents/research
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml
```

**Benefits of `uv tool` installation:**
- ✅ Isolated Python environment (no conflicts with system Python)
- ✅ Available globally from any directory
- ✅ Editable mode (`-e .`) allows live development
- ✅ Easy updates with `git pull` (editable mode)
- ✅ Clean uninstall with `uv tool uninstall massgen`

#### Working Across Multiple Projects

```bash
# Project 1: Web development
cd ~/projects/website
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml
# Adds ~/projects/website as context path

# Project 2: Data analysis
cd ~/data/analytics
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml
# Adds ~/data/analytics as context path

# Project 3: Documentation
cd ~/docs/user-manual
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml
# Adds ~/docs/user-manual as context path
```

Each project gets its own `.massgen/` directory with isolated workspaces, sessions, and snapshots.

#### Best Practices

1. **Store configs centrally**: Keep your config files in `~/.massgen/configs/` or `~/massgen-configs/`
2. **Use relative paths**: Config files use relative paths that get auto-relocated to `.massgen/`
3. **Add to gitignore**: Add `.massgen/` to `.gitignore` in each project
4. **Share configs**: Reuse the same config across different projects - context paths are added interactively

**Example config for multi-directory use:**
```yaml
agents:
  - id: "agent1"
    backend:
      type: "openai"
      model: "gpt-4"
      cwd: "workspace1"  # Auto-relocated to .massgen/workspaces/workspace1/

orchestrator:
  snapshot_storage: "snapshots"  # Auto-relocated to .massgen/snapshots/
  agent_temporary_workspace: "temp_workspaces"  # Auto-relocated to .massgen/temp_workspaces/
  # No context_paths needed - added interactively when you run massgen
```

This config works in **any directory** - just `cd` to your project and run `massgen`!

### .massgen Directory Structure

MassGen automatically organizes all state files under a `.massgen/` directory for clean project organization:

```
your-project/
├── .massgen/                          # All MassGen state
│   ├── sessions/                      # Multi-turn conversation history
│   ├── workspaces/                    # Agent working directories
│   │   ├── workspace1/
│   │   └── workspace2/
│   ├── snapshots/                     # Workspace snapshots
│   └── temp_workspaces/               # Previous turn results
├── massgen/                               # Your project files
├── .env                               # Protected from agent writes
└── .git/                              # Protected from agent writes
```

**Benefits:**
- ✅ **Clean Projects**: All MassGen files contained in one directory
- ✅ **Easy Gitignore**: Just add `.massgen/` to `.gitignore`
- ✅ **Portable**: Move or delete `.massgen/` without affecting your project
- ✅ **Protected Workspaces**: Even if `.massgen` is in excluded patterns, workspace paths inside can be fully writable

**Path relocation** happens automatically:
- Relative paths in config are relocated under `.massgen/`
- Absolute paths and paths already under `.massgen/` are left unchanged
- Applies to: `cwd`, `snapshot_storage`, `agent_temporary_workspace`

**File Delivery Challenge:**
When `.massgen/` is inside a context path with write permission (e.g., user adds `/home/user/project/` as writable context), agents might mistakenly think that creating files in their workspace (`.massgen/workspaces/`) satisfies the delivery requirement. This is incorrect - the workspace is just a staging area.

**Solution:**
The system prompt explicitly warns agents: **"Files inside `.massgen/` do NOT count as delivered."** The final agent must explicitly copy or write files from the workspace to the actual target context path using full absolute paths. This ensures deliverables end up in the user's project directory, not buried in `.massgen/`.

### Real-World Example

Based on the filesystem permissions test configuration (`fs_permissions_test.yaml`):

```yaml
agents:
  - id: "gpt5nano_1"
    backend:
      type: "openai"
      model: "gpt-5"
      cwd: "workspace1"                      # Isolated workspace for this agent

  - id: "gpt5nano_2"
    backend:
      type: "openai"
      model: "gpt-5"
      cwd: "workspace2"                      # Separate isolated workspace

orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"
  context_paths:
    - path: "/home/nick/GitHubProjects/MassGen/v0.0.21-example"
      permission: "write"                    # Final agent can modify this project directory
```

**What happens:**
1. **Both agents** can read files from `/home/nick/GitHubProjects/MassGen/v0.0.21-example`
2. **Context agent** (`gpt5nano_1`) gets READ-only access during coordination
3. **Final agent** (`gpt5nano_2`) gets WRITE access and can modify project files
4. **Each agent** has full WRITE access to their own workspace (`workspace1`, `workspace2`)
5. **Temporary workspaces** allow agents to share context from previous coordination rounds

## Snapshot Management and Agent Coordination

### Overview

During multi-agent coordination, MassGen uses a snapshot-based system to enable context sharing between agents. This ensures that all agents can see each other's work (complete or partial) and collaborate effectively.

### When Snapshots Are Saved

Snapshots are workspace copies saved at specific coordination points:

**1. Completed Answers:**
- Agent provides a complete answer via `new_answer` tool
- Workspace snapshot saved to `snapshot_storage/{agent_id}/`
- Snapshot overwrites previous one (keeps only most recent)
- Also saved to log directories with timestamp for debugging

**2. Completed Votes:**
- Agent votes for another agent's answer via `vote` tool
- Workspace snapshot saved (captures any work done before voting)

**3. Partial Work on Restart (NEW):**
- Agent is interrupted mid-answer due to another agent providing a new answer
- All other agents get `restart_pending = True` flag
- **Before restarting, agent's partial workspace is saved as a snapshot**
- This ensures other agents can see the partial work in their temp workspaces
- Critical for preserving incremental progress during coordination

### Workspace Lifecycle

| Location | When Cleared | Purpose |
|----------|-------------|---------|
| **Agent workspace** (`workspace1/`) | After saving snapshot (except final) | Clean slate for next execution |
| **Temp workspace** (`temp_workspaces/{agent_id}/`) | Before each agent execution | Fresh copy of all other agents' latest work |
| **Temp workspace parent** | At orchestration startup | Remove stale data from previous runs |
| **Snapshot storage** (`snapshots/{agent_id}/`) | When new snapshot saved | Overwritten with latest (only most recent kept) |

### Context Sharing Flow

**1. Snapshot Storage** (`snapshot_storage/{agent_id}/`):
- Source of truth for each agent's latest work
- Only most recent snapshot kept (overwritten on each save)
- Contains complete OR partial work, whichever is most recent

**2. Temporary Workspaces** (`temp_workspaces/{agent_id}/`):
- Populated before each agent execution via `_copy_all_snapshots_to_temp_workspace()`
- Contains all OTHER agents' latest snapshots
- Uses anonymous IDs (agent1, agent2, etc.) for privacy
- Read-only access for agents

**3. Agent Workspace** (`workspace1/`, `workspace2/`):
- Agent's personal working directory
- Full write access
- Cleared after saving snapshot (to prepare for restart)

### Restart and Partial Work Preservation

When an agent is restarted due to new answers from other agents:

```python
# orchestrator.py: Agent restart sequence
1. Detect restart_pending flag is True
2. Call _save_partial_work_on_restart(agent_id)
   - Saves current workspace state to snapshots/
   - Logs workspace contents for debugging
   - Preserves any files created during partial execution
3. Clear workspace (prepare for fresh start)
4. Agent restarts with access to:
   - All other agents' snapshots in temp_workspaces/
   - Including the partial work from interrupted agents
```

**Example Coordination Flow:**

```
Round 1:
- Agent A starts → writes files to workspace1/
- Agent B starts → writes files to workspace2/
- Agent A completes answer → snapshot saved to snapshots/agentA/
- Agent B gets restart_pending=True (new answer detected)
- Agent B's partial work saved → snapshot saved to snapshots/agentB/
- Agent B's workspace cleared

Round 2:
- Agent A restarts
  - temp_workspaces/agentA/ now contains agentB's partial work
  - Can see what Agent B was working on
- Agent B restarts
  - temp_workspaces/agentB/ contains agentA's complete answer
  - Can build upon Agent A's completed work
```

**Key Design Decision:** Partial work is ALWAYS saved before restart. This ensures:
- No work is lost during agent restarts
- All agents can see each other's progress (complete or partial)
- Better collaboration through incremental visibility
- Debugging is easier with complete workspace history

### Implementation Details

**Snapshot Save Method** (`filesystem_manager.py:save_snapshot()`):
1. Copies workspace contents to `snapshot_storage/{agent_id}/` (overwrites existing)
2. Also saves to log directories: `log_session/agent_id/timestamp/workspace/`
3. Does NOT clear workspace (clearing happens separately)

**Partial Work Save** (`orchestrator.py:_save_partial_work_on_restart()`):
```python
async def _save_partial_work_on_restart(self, agent_id: str) -> None:
    """Save partial work before restarting due to new answers from others."""
    await self._save_agent_snapshot(
        agent_id,
        answer_content=None,  # No complete answer yet
        context_data=self.get_last_context(agent_id),
        is_final=False,
    )
```

**Temp Workspace Population** (`orchestrator.py:_copy_all_snapshots_to_temp_workspace()`):
1. Collects all snapshots from `snapshot_storage/{agent_id}/` directories
2. Clears existing temp workspace for target agent
3. Copies all other agents' snapshots using anonymous IDs
4. Agent can now read other agents' work through temp workspace

## Permission Validation Flow

### 1. Path Resolution
```python
# PathPermissionManager resolves and validates paths
resolved_path = path.resolve()
permission = self.get_permission(resolved_path)
```

### 2. Permission Check
```python
async def pre_tool_use_hook(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate tool calls based on permissions."""
    if self._is_write_tool(tool_name):
        return self._validate_write_tool(tool_name, tool_args)
    return (True, None)  # Allow read operations and non-file tools
```

### 3. Backend-Specific Enforcement

#### Function-based Backends (OpenAI responses, Chat Completions, Claude)
```python
# Base class sets up per-agent function hooks
self.function_hook_manager = FunctionHookManager()
permission_hook = PathPermissionManagerHook(
    self.filesystem_manager.path_permission_manager
)
self.function_hook_manager.register_global_hook(HookType.PRE_CALL, permission_hook)
```

#### Session-based Backends (Gemini)
```python
# Convert sessions to permission-aware sessions
from ..mcp_tools.hooks import convert_sessions_to_permission_sessions
mcp_sessions = convert_sessions_to_permission_sessions(
    mcp_sessions,
    self.filesystem_manager.path_permission_manager
)
```

**Fallback Behavior**: If MCP SDK is not available, Gemini gracefully falls back to workflow tools only (no filesystem access). This eliminates the need for permission validation since no file operations are possible.

#### Special Backends (Claude Code)
```python
# Claude Code uses native filesystem tools with hook integration
# Hooks are passed directly to ClaudeCodeOptions
hooks_config = self.filesystem_manager.get_claude_code_hooks_config()

options = {
    "cwd": workspace_path,
    "permission_mode": "acceptEdits",
    "allowed_tools": allowed_tools,
}

# Add hooks if available
if hooks_config:
    options["hooks"] = hooks_config

return ClaudeCodeOptions(**options)
```

## Implementing Backend Support

### Step 1: Extend LLMBackend

```python
from .base import LLMBackend, FilesystemSupport

class NewBackend(LLMBackend):
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        # Backend initialization
```

### Step 2: Declare Filesystem Support

```python
def get_filesystem_support(self) -> FilesystemSupport:
    """Declare what type of filesystem support this backend provides."""
    # Choose based on your backend's capabilities:
    return FilesystemSupport.NONE      # No filesystem support
    return FilesystemSupport.NATIVE    # Built-in filesystem tools (like Claude Code)
    return FilesystemSupport.MCP       # Filesystem through MCP servers
```

### Step 3: Configure Parameter Exclusions

```python
# Use base class exclusions to avoid API parameter conflicts
excluded_params = self.get_base_excluded_config_params().union({
    "backend_specific_param1",
    "backend_specific_param2",
})

# Filter parameters before API calls
api_params = {k: v for k, v in all_params.items()
              if k not in excluded_params and v is not None}
```

### Step 4: Implement Permission Hooks (if needed)

#### For Function-based Backends
```python
# Use default base class behavior - no override needed
# Base class automatically sets up FunctionHookManager with permission hooks
```

#### For Session-based Backends
```python
def _setup_permission_hooks(self):
    """Session-based backends use MCP session wrapping for permissions."""
    # Override to prevent function hook creation - permissions handled at session level
    logger.debug("[Backend] Using session-based permissions, skipping function hook setup")

# In your session creation code:
if self.filesystem_manager:
    from ..mcp_tools.hooks import convert_sessions_to_permission_sessions
    sessions = convert_sessions_to_permission_sessions(
        sessions,
        self.filesystem_manager.path_permission_manager
    )
```

**Why Override is Necessary**: Without the override, backends would create unused `FunctionHookManager` instances while using session-based permissions, leading to resource waste and debugging confusion. When MCP SDK is unavailable, session-based backends fall back to workflow tools only (no filesystem access), making permission validation unnecessary.

#### For Special Backends (Claude Code)
```python
def _setup_permission_hooks(self):
    """Claude Code uses native filesystem tools with built-in hook support."""
    # Claude Code hooks are passed via ClaudeCodeOptions, not function hooks
    # No function hook manager needed - permissions handled at tool level
    pass

# In your client setup:
hooks_config = {}
if self.filesystem_manager:
    hooks_config = self.filesystem_manager.get_claude_code_hooks_config()

options = ClaudeCodeOptions(
    cwd=workspace_path,
    hooks=hooks_config,  # Native Claude Code hook integration
    # ... other options
)
```


## Security Considerations

### Path Validation
- All paths are resolved to absolute paths to prevent directory traversal
- Workspace boundaries are enforced to prevent cross-agent access
- Dangerous commands are blocked regardless of permissions
- **Default System File Exclusions**: Certain paths are automatically protected from write access regardless of context path permissions

### Default Excluded Patterns

The following paths are **always excluded from write access** as system-level defaults to prevent accidental modification of critical files:

```python
DEFAULT_EXCLUDED_PATTERNS = [
    ".massgen",      # MassGen state directory
    ".env",          # Environment variables
    ".git",          # Git repository data
    "node_modules",  # Node.js dependencies
    "__pycache__",   # Python bytecode cache
    ".venv",         # Python virtual environment
    "venv",          # Python virtual environment (alternate name)
    ".pytest_cache", # Pytest cache
    ".mypy_cache",   # Mypy type checker cache
    ".ruff_cache",   # Ruff linter cache
    ".DS_Store",     # macOS metadata
    "massgen_logs",  # MassGen log files
]
```

**Behavior:**
- These patterns are checked against all path components
- If any part of a path matches an excluded pattern, it becomes read-only
- **Exception**: Workspace paths (agent's `cwd`) override exclusions - agents can write within their own workspace even if it's under `.massgen/workspaces/`
- Context paths with write permission will still have these specific files/directories protected

**Example:**
```yaml
orchestrator:
  context_paths:
    - path: "/home/user/project"
      permission: "write"
```

Even with write permission, the agent **cannot** modify:
- `/home/user/project/.env`
- `/home/user/project/.git/`
- `/home/user/project/node_modules/`

But the agent **can** write to their workspace:
- `/home/user/project/.massgen/workspaces/workspace1/` (full write access)

### Path Priority Resolution

When multiple managed paths could match a given file path, MassGen uses **depth-first priority**:

1. **More specific (deeper) paths take precedence** over parent paths
2. Paths are sorted by depth (number of path components) in descending order
3. The first matching path determines the permission

**Example:**

```yaml
orchestrator:
  context_paths:
    - path: "/home/user/project"              # Depth: 4 parts
      permission: "read"
```

Agent configuration:
```yaml
agents:
  - id: "agent1"
    backend:
      cwd: "/home/user/project/.massgen/workspaces/workspace1"  # Depth: 7 parts
```

When checking `/home/user/project/.massgen/workspaces/workspace1/index.html`:
1. First checks workspace path (depth 7) → **WRITE** ✅ (workspace always writable)
2. Never reaches context path (depth 4) → read permission not applied

This ensures workspace paths always take precedence over their parent context paths.

### Permission Isolation
- Each agent gets its own `FunctionHookManager` instance
- No global state sharing between agents
- Context paths are validated on every access

### Dangerous Operation Prevention
```python
def _validate_command_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Block dangerous system commands."""
    dangerous_patterns = [
        "rm ", "rm -", "rmdir", "del ",
        "sudo ", "su ", "chmod ", "chown ",
        "format ", "fdisk", "mkfs",
    ]
    # Block dangerous operations regardless of permissions
```

## Troubleshooting

### Common Issues

#### "0 pre-tool hooks" in logs
**Cause**: Backend not passing permission hooks to tool execution
**Solution**: Ensure hooks are passed to MCP client or function execution

#### "Unexpected keyword argument" errors
**Cause**: Backend passing MassGen-specific parameters to API
**Solution**: Use `get_base_excluded_config_params()` for parameter filtering

#### Permission denied for workspace files
**Cause**: Incorrect path resolution or workspace setup
**Solution**: Verify workspace paths are properly added to `PathPermissionManager`

### Debugging

Enable detailed logging to trace permission validation:

```python
logger.debug(f"[PathPermissionManager] Validating {tool_name} for path: {path}")
logger.debug(f"[PathPermissionManager] Found permission: {permission}")
logger.debug(f"[PathPermissionManager] Managed paths: {self.managed_paths}")
```

## Migration Guide

### Upgrading Existing Backends

1. **Update parameter exclusions**:
   ```python
   # Old approach
   excluded_params = {"cwd", "agent_id", "type"}

   # New approach
   excluded_params = self.get_base_excluded_config_params().union({
       "backend_specific_param"
   })
   ```

2. **Override permission hooks if needed**:
   ```python
   def _setup_permission_hooks(self):
       """Override for backends that don't use function hooks."""
       if self.get_filesystem_support() == FilesystemSupport.MCP:
           pass  # Use MCP-level hooks instead
       else:
           super()._setup_permission_hooks()  # Use default function hooks
   ```

3. **Add filesystem support declaration**:
   ```python
   def get_filesystem_support(self) -> FilesystemSupport:
       return FilesystemSupport.MCP  # or NATIVE/NONE based on capabilities
   ```

## Examples

This section provides complete examples demonstrating MassGen's filesystem capabilities across different scenarios.

### Single-Turn Web Development

**Scenario**: Create a coding puzzle game with Vite
**Config**: `massgen/configs/tools/filesystem/gemini_gpt5_filesystem_casestudy.yaml`

```bash
# Navigate to your project directory
cd ~/projects/coding-puzzles

# Run MassGen with filesystem support
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_casestudy.yaml \
  "Build a game where users see a diverse set of up-to-date small, static coding puzzles related to common coding bugs. Then, award them points if they can clearly spot the error in the code. Use Vite with a package.json with minimal dependencies."

# Prompted to add current directory as context path
❓ Add current directory as context path?
   /Users/user/projects/coding-puzzles
   [Y]es (default) / [N]o / [C]ustom path: [Enter]

✓ Added /Users/user/projects/coding-puzzles (write)
```

**Config file:**
```yaml
agents:
  - id: "gemini"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      cwd: "workspace1"  # Auto-relocated to .massgen/workspaces/workspace1/

  - id: "gemini2"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      cwd: "workspace2"  # Auto-relocated to .massgen/workspaces/workspace2/

orchestrator:
  snapshot_storage: "snapshots"  # Auto-relocated to .massgen/snapshots/
  agent_temporary_workspace: "temp_workspaces"  # Auto-relocated to .massgen/temp_workspaces/
  # context_paths added interactively
```

**Result**: Game files delivered to `/Users/user/projects/coding-puzzles/` with MassGen state in `.massgen/`

### Multi-Turn Interactive Development

**Scenario**: Iterative development across multiple conversation turns
**Config**: `massgen/configs/tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn.yaml`

```bash
# Start interactive session
cd ~/projects/web-app
uv tool run massgen --config tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn.yaml

# Turn 1: Create basic structure
User: "Create a React app with authentication"
Assistant: [Creates basic React app with login/logout]
Files delivered to: ~/projects/web-app/

# Turn 2: Add features building on Turn 1
User: "Add user profile management"
Assistant: [Builds upon existing React app, adds profile features]
Files delivered to: ~/projects/web-app/ (updated)

# Turn 3: Further refinements
User: "Add password reset functionality"
Assistant: [References previous turns, adds password reset to existing app]
```

**Config file:**
```yaml
agents:
  - id: "gemini"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      cwd: "workspace1"

  - id: "gemini2"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      cwd: "workspace2"

orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"
  session_storage: "sessions"  # Enables multi-turn persistence
```

**File Structure After 3 Turns:**
```
~/projects/web-app/
├── .massgen/
│   ├── sessions/session_20250928_143022/
│   │   ├── SESSION_SUMMARY.txt
│   │   ├── turn_1/
│   │   │   ├── workspace/  # Turn 1 final output
│   │   │   ├── answer.txt
│   │   │   └── metadata.json
│   │   ├── turn_2/
│   │   │   └── ...  # Turn 2 results
│   │   └── turn_3/
│   │       └── ...  # Turn 3 results
│   ├── workspaces/
│   │   ├── workspace1/  # Agent workspaces
│   │   └── workspace2/
│   └── logs/log_20250928_143022/
│       ├── turn_1/massgen_debug.log
│       ├── turn_2/massgen_debug.log
│       └── turn_3/massgen_debug.log
├── src/          # Your actual React app
├── package.json  # Project files delivered by agents
└── README.md
```

#### Alternative Multi-Turn Config with Mixed Backends

**Config**: `massgen/configs/tools/filesystem/multiturn/grok4_gpt5_claude_code_filesystem_multiturn.yaml`

```bash
# Multi-backend approach: Grok + GPT-5 for diverse perspectives
cd ~/projects/complex-app
uv tool run massgen --config tools/filesystem/multiturn/grok4_gpt5_claude_code_filesystem_multiturn.yaml
```

**Config highlights:**
```yaml
agents:
  - id: "agent_a"
    backend:
      type: "grok"
      model: "grok-4-fast-reasoning"
      cwd: "workspace1"

  - id: "agent_b"
    backend:
      type: "openai"
      model: "gpt-5-mini"
      reasoning:
        effort: "medium"
      cwd: "workspace2"

orchestrator:
  session_storage: "sessions"  # Multi-turn persistence
```

This config provides diverse agent perspectives while maintaining the same multi-turn workflow.

### Working with Existing Codebases

**Scenario**: Debug and fix issues in an existing project

```bash
# Navigate to existing project with issues
cd ~/projects/existing-app

# Run MassGen to analyze and fix
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_casestudy.yaml \
  "The authentication is broken - users can't log in. Find and fix the issue."

# Add current directory for analysis and fixes
❓ Add current directory as context path?
   /Users/user/projects/existing-app
   [Y]es (default) / [N]o / [C]ustom path: [Enter]

✓ Added /Users/user/projects/existing-app (write)
```

**Agent Process:**
1. **Read existing code** from context path: `/Users/user/projects/existing-app/`
2. **Analyze** authentication flow in current codebase
3. **Work in workspace**: `.massgen/workspaces/workspace1/`
4. **Deliver fixes** to context path: `/Users/user/projects/existing-app/`

**Key Benefit**: Agents understand existing code structure and fix issues in place

### Permission Scenarios

#### Read-Only Analysis
```yaml
orchestrator:
  context_paths:
    - path: "/path/to/legacy-system"
      permission: "read"  # Analysis only, no modifications
```

#### Multiple Context Paths
```yaml
orchestrator:
  context_paths:
    - path: "/path/to/shared-library"
      permission: "read"    # Reference existing code
    - path: "/path/to/my-project"
      permission: "write"   # Deliver new code here
```

#### File Context Paths (Individual Files)
```yaml
orchestrator:
  context_paths:
    - path: "/path/to/config.yaml"
      permission: "read"    # Only this file is accessible
    - path: "/path/to/logo.png"
      permission: "read"    # Share specific assets without exposing directory
```

**How it works:**
- Agent can read `/path/to/config.yaml` ✅
- Agent **cannot** read `/path/to/other_file.txt` ❌ (sibling files blocked)
- Agent **cannot** list `/path/to/` directory ❌
- Only the explicitly specified file is accessible

**Use cases:**
- Share specific configuration files without exposing secrets
- Provide reference images/assets without directory access
- Grant access to individual data files for analysis

**Interactive example:**
```bash
❓ Add current directory as context path?
   /home/user/project
   [Y]es (default) / [P]rotected / [N]o / [C]ustom path: c
   Enter path (absolute or relative, file or directory): ./config.yaml
   Permission [read/write] (default: write): read
✓ Added /home/user/project/config.yaml (read)
```

#### System File Protection
Even with write permission, these paths are automatically protected:
- `/path/to/my-project/.env` → Always read-only
- `/path/to/my-project/.git/` → Always read-only
- `/path/to/my-project/node_modules/` → Always read-only
- `/path/to/my-project/.massgen/` → Always read-only (except agent workspaces)

### Directory-Based Workflow Patterns

#### Pattern 1: New Project Creation
```bash
mkdir ~/projects/new-app
cd ~/projects/new-app
uv tool run massgen --config <config> "Create a new Express.js API"
# Result: New project files in ~/projects/new-app/
```

#### Pattern 2: Existing Project Enhancement
```bash
cd ~/projects/existing-app  # Contains package.json, src/, etc.
uv tool run massgen --config <config> "Add GraphQL support"
# Result: GraphQL files added to existing structure
```

#### Pattern 3: Cross-Project Development
```bash
cd ~/projects/mobile-app
# Custom path to shared component library
uv tool run massgen --config <config>
# Custom path: ~/shared/ui-components (read-only reference)
# Target: ~/projects/mobile-app (write access)
```

### Error Scenarios and Solutions

#### Missing Context Path
```bash
# Error: Context path doesn't exist
Error: Context paths not found:
  - /path/that/does/not/exist

# Solution: Create directory first or use correct path
mkdir /path/that/does/not/exist
```

#### Sibling File Access Blocked (File Context Paths)
```bash
# Scenario: Added /project/config.yaml as file context path
# Agent tries to access sibling file
Tool: read_file
Path: /project/secrets.yaml
Result: ❌ Access denied: '/project/secrets.yaml' is not an explicitly allowed file in this directory

# Solution: This is working as intended!
# Only the explicitly added file is accessible
# To allow access to other files, add them as separate context paths:
context_paths:
  - path: "/project/config.yaml"
    permission: "read"
  - path: "/project/secrets.yaml"  # Add explicitly if needed
    permission: "read"

# Or add the entire directory instead:
context_paths:
  - path: "/project"
    permission: "read"
```

#### Delivery Confusion
```bash
# Problem: Files created in workspace but not delivered
Files created:
- .massgen/workspaces/workspace1/app.js  # ❌ Not delivered

# Solution: Agent must copy to context path
Files delivered:
- /path/to/project/app.js  # ✅ Delivered to target
```

## Related Documentation

- **Multi-Turn Design**: `docs/dev_notes/multi_turn_filesystem_design.md` - Detailed architecture for session persistence and turn-based workflows
- **MCP Integration**: `docs/dev_notes/gemini_filesystem_mcp_design.md` - How filesystem access works through Model Context Protocol
- **Context Sharing**: `docs/dev_notes/v0.0.14-context.md` - Original context sharing design
- **User Context Paths**: `docs/source/examples/case_studies/user-context-path-support-with-copy-mcp.md` - Case study on adding user-specified paths
- **Claude Code Workspace**: `docs/source/examples/case_studies/claude-code-workspace-management.md` - Native filesystem integration patterns

## Conclusion

MassGen's permissions system provides secure, granular access control for multi-agent workflows while maintaining simplicity for backend implementers. The system automatically handles the complexity of permission validation while allowing backends to focus on their core functionality.

**Key Features:**
- ✅ **File and directory context paths**: Share individual files or entire directories
- ✅ **Sibling file isolation**: File context paths prevent access to other files in the same directory
- ✅ **Protected paths**: Mark specific files/directories as immune from modification
- ✅ **Interactive configuration**: Add context paths without editing YAML files
- ✅ **Automatic path validation**: Prevents common misconfigurations
- ✅ **MCP integration**: Works seamlessly with MCP filesystem servers

For new backends, simply extend `LLMBackend`, declare your filesystem support level, and the base class handles the rest. The system scales from simple file access to complex multi-project workflows with cross-drive support and granular file-level permissions.
