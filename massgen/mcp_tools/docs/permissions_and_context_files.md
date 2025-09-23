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

**Orchestrator Level:**
- `context_paths`: List of user-specified paths with permissions applied to all agents
  - `path`: Absolute path to directory or file
  - `permission`: "read" or "write" - determines final agent access (context agents always read-only)
- `snapshot_storage`: Directory for storing agent workspace snapshots
- `agent_temporary_workspace`: Parent directory for temporary workspaces

**Permission Behavior:**
- **Context agents**: Always get READ access to context paths regardless of permission setting
- **Final agent**: Gets the configured permission (READ or WRITE) for context paths
- **Workspace (`cwd`)**: Always WRITE access for the owning agent

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

## Conclusion

MassGen's permissions system provides secure, granular access control for multi-agent workflows while maintaining simplicity for backend implementers. The system automatically handles the complexity of permission validation while allowing backends to focus on their core functionality.

For new backends, simply extend `LLMBackend`, declare your filesystem support level, and the base class handles the rest. The system scales from simple file access to complex multi-project workflows with cross-drive support.
