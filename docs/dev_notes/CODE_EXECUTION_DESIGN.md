# Code Execution System Design

**Issues:** #295
**Author:** MassGen Team
**Date:** 2025-10-12
**Status:** Complete (Local Execution)

## Overview

This design doc covers the implementation of local code execution for all backends via a single MCP command execution tool. The system provides AG2-inspired security with PathPermissionManager enforcement.

## Problem Statement

Currently, only Claude Code backend can execute bash commands. This limitation prevents other backends (OpenAI, Gemini, Grok, etc.) from:
- Running unit tests they write
- Executing code for self-improvement
- Installing packages and managing dependencies
- Performing command-line operations

**Solution:** Implement a single `execute_command` MCP tool that works with all backends, with comprehensive security through PathPermissionManager hooks.

## Goals

### Primary Goals (Issue #295)
1. ✅ Enable code execution for all backends through a single MCP tool
2. ✅ Implement local execution with AG2-inspired security
3. ✅ Integrate with PathPermissionManager for workspace enforcement
4. ✅ Support command filtering (whitelist/blacklist)
5. ✅ Auto-detect virtual environments per workspace
6. ✅ Comprehensive test coverage and documentation

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Backend (Any)                         │
│                   (OpenAI, Claude, Gemini, Grok, etc.)      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ MCP Protocol
                         │
┌────────────────────────┴────────────────────────────────────┐
│                   Code Execution MCP Server                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Single Tool: execute_command                         │  │
│  │                                                        │  │
│  │  execute_command(command, timeout, work_dir)         │  │
│  │                                                        │  │
│  │  Examples:                                            │  │
│  │    execute_command("python test.py")                 │  │
│  │    execute_command("pytest tests/ -v")               │  │
│  │    execute_command("pip install requests")           │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────┴──────────────────────────────┐ │
│  │           Security Layers                             │ │
│  │  1. AG2-inspired sanitization (dangerous patterns)   │ │
│  │  2. Command filtering (whitelist/blacklist)          │ │
│  │  3. PathPermissionManager hooks (PreToolUse)         │ │
│  │  4. Path validation (workspace confinement)          │ │
│  │  5. Timeout enforcement                               │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ subprocess.run()
                         │
┌────────────────────────┴────────────────────────────────────┐
│              Local Shell Execution                           │
│  - Executes in workspace directory                          │
│  - Auto-detects .venv per workspace                         │
│  - Captures stdout/stderr                                    │
│  - Returns structured results                                │
└─────────────────────────────────────────────────────────────┘
```

### Security Integration

```
┌─────────────────────────────────────────────────────────────┐
│                  PathPermissionManager                       │
│  PreToolUse Hook (executes before tool call)                │
│  ┌────────────────────────────────────────────────────────┐│
│  │ command_tools = {"Bash", "bash", "shell", "exec",     ││
│  │                  "execute_command"}  ← Added          ││
│  │                                                        ││
│  │ Validates:                                            ││
│  │  - Dangerous patterns (rm -rf, sudo, etc.)           ││
│  │  - Write operations to read-only context paths       ││
│  │  - Access outside workspace directory                 ││
│  └────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                         │
                         │ HookResult(allowed, reason)
                         │
┌────────────────────────┴────────────────────────────────────┐
│               Code Execution MCP Server                      │
│  If allowed → execute_command proceeds                      │
│  If blocked → returns error with reason                     │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Design

### 1. Code Execution MCP Server

**Location:** `massgen/filesystem_manager/_code_execution_server.py`

**Single Tool:**

```python
@mcp.tool()
def execute_command(
    command: str,
    timeout: int = 60,
    work_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a command line command.

    This tool allows executing any command line program including:
    - Python: execute_command("python script.py")
    - Node.js: execute_command("node app.js")
    - Tests: execute_command("pytest tests/")
    - Build: execute_command("npm run build")
    - Any shell command: execute_command("ls -la")

    Args:
        command: The command to execute
        timeout: Maximum execution time in seconds (default: 60)
        work_dir: Working directory for execution (relative to workspace)

    Returns:
        Dictionary with:
        - success: bool
        - exit_code: int
        - stdout: str
        - stderr: str
        - execution_time: float

    Security:
        - Execution is confined to allowed paths
        - Timeout enforced to prevent infinite loops
        - In Docker mode: full container isolation
    """
```

**Implementation:**

```python
async def create_server() -> fastmcp.FastMCP:
    """Factory function to create code execution MCP server."""

    parser = argparse.ArgumentParser(description="Code Execution MCP Server")
    parser.add_argument(
        "--allowed-paths",
        type=str,
        nargs="*",
        default=[],
        help="List of allowed base paths for execution"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Default timeout in seconds"
    )
    parser.add_argument(
        "--max-output-size",
        type=int,
        default=1024 * 1024,  # 1MB
        help="Maximum output size in bytes"
    )
    parser.add_argument(
        "--allowed-commands",
        type=str,
        nargs="*",
        default=None,
        help="Whitelist regex patterns (e.g., 'python.*', 'pytest.*')"
    )
    parser.add_argument(
        "--blocked-commands",
        type=str,
        nargs="*",
        default=None,
        help="Blacklist regex patterns (e.g., 'rm.*', 'sudo.*')"
    )
    args = parser.parse_args()

    mcp = fastmcp.FastMCP("Command Execution")

    # Store configuration
    mcp.allowed_paths = [Path(p).resolve() for p in args.allowed_paths]
    mcp.default_timeout = args.timeout
    mcp.max_output_size = args.max_output_size
    mcp.allowed_commands = args.allowed_commands
    mcp.blocked_commands = args.blocked_commands

    @mcp.tool()
    def execute_command(
        command: str,
        timeout: Optional[int] = None,
        work_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        # 1. Sanitize dangerous commands (AG2-inspired)
        # 2. Check whitelist/blacklist filters
        # 3. Prepare environment (auto-detect .venv)
        # 4. Execute via subprocess.run()
        # 5. Return structured results
        pass

    return mcp
```

### 2. FilesystemManager Integration

**Extend:** `massgen/filesystem_manager/_filesystem_manager.py`

**New Configuration:**

```python
def __init__(
    self,
    cwd: str,
    # ... existing params ...
    enable_mcp_command_line: bool = False,
    command_line_allowed_commands: Optional[List[str]] = None,
    command_line_blocked_commands: Optional[List[str]] = None,
):
    # ... existing initialization ...

    self.enable_mcp_command_line = enable_mcp_command_line
    self.command_line_allowed_commands = command_line_allowed_commands
    self.command_line_blocked_commands = command_line_blocked_commands
```

**New Method:**

```python
def get_command_line_mcp_config(self) -> Dict[str, Any]:
    """
    Generate command line execution MCP server configuration.

    Returns:
        Dictionary with MCP server configuration for command execution
    """
    script_path = Path(__file__).parent / "_code_execution_server.py"

    args = [
        "run",
        f"{script_path}:create_server",
        "--",
        "--allowed-paths"
    ] + self.path_permission_manager.get_mcp_filesystem_paths()

    # Add command filtering if configured
    if self.command_line_allowed_commands:
        args.extend(["--allowed-commands"] + self.command_line_allowed_commands)
    if self.command_line_blocked_commands:
        args.extend(["--blocked-commands"] + self.command_line_blocked_commands)

    config = {
        "name": "command_line",
        "type": "stdio",
        "command": "fastmcp",
        "args": args,
        "cwd": str(self.cwd),
    }

    return config
```

**Update inject_filesystem_mcp:**

```python
def inject_filesystem_mcp(self, backend_config: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing filesystem and workspace_tools injection ...

    # Add command line MCP tool if enabled
    if self.enable_mcp_command_line and "command_line" not in existing_names:
        mcp_servers.append(self.get_command_line_mcp_config())

    return backend_config
```

### 3. Security Considerations

**Multi-Layer Security:**

1. **AG2-Inspired Sanitization** (First layer, always applied):
   - `rm -rf /` - Root deletion blocked
   - `dd` - Disk write blocked
   - Fork bombs - Process bombs blocked
   - `/dev` writes - Direct device writes blocked
   - `/dev/null` moves - File destruction blocked
   - `sudo` - Privilege escalation blocked
   - `su` - User switching blocked
   - `chmod` - Permission changes blocked
   - `chown` - Ownership changes blocked

2. **Command Filtering** (Second layer, user-configurable):
   - **Whitelist**: Only allow specific command patterns (e.g., `["python.*", "pytest.*"]`)
   - **Blacklist**: Block specific command patterns (e.g., `["rm.*", "git push.*"]`)
   - Patterns use `re.match()` - use `"pytest.*"` not `"pytest .*"` to match bare commands

3. **PathPermissionManager Integration** (Third layer, hook-based):
   - **Added to command_tools set** (_path_permission_manager.py:454)
   - `execute_command` validated like `Bash` via PreToolUse hooks
   - Validates dangerous patterns in commands
   - Blocks write operations to read-only context paths
   - Prevents access outside workspace directory
   - Comprehensive test coverage (93 new test lines)

4. **Path Validation** (Fourth layer):
   - Working directory must be within allowed paths
   - Path resolution and validation before execution

5. **Resource Limits** (Fifth layer):
   - Timeout enforcement prevents infinite loops (default: 60s)
   - Output size limits prevent memory exhaustion (default: 1MB)
   - Captures and truncates stdout/stderr if too large

## Implementation Plan

### Phase 1: Local Code Execution (Issue #295) - ✅ COMPLETE
1. ✅ Explore codebase structure
2. ✅ Create design document
3. ✅ Implement `_code_execution_server.py` with single `execute_command` tool
4. ✅ Add local mode with subprocess (AG2-inspired sanitization)
5. ✅ Integrate with FilesystemManager
6. ✅ Write unit tests (350 lines, 11 test classes)
7. ✅ Add virtual environment support (auto-detect per workspace)
8. ✅ Add command filtering (whitelist/blacklist with regex)
9. ✅ Create example configurations in `massgen/configs/tools/code-execution/`
10. ✅ Integrate with PathPermissionManager (PreToolUse hooks)
11. ✅ Add permission validation tests (93 new test lines)
12. ✅ Fix regex pattern matching (document bare command matching)
13. ✅ Auto-generated file exclusions (`__pycache__`, `.pyc`, etc.)
14. ✅ Code execution result guidance in system messages
15. ⏳ Test with OpenAI, Gemini, Grok backends in production

### Phase 2: Docker Support (Issue #304) - 🔮 FUTURE
- Deferred for future release
- Local execution provides baseline security
- Docker would add container isolation layer
- See "Future Enhancements" section below

## Auto-Generated File Handling

When agents execute code (e.g., running pytest), they generate temporary files like `__pycache__`, `.pyc`, `.pytest_cache`, etc. These files:
- Don't need to be read by agents (waste of tokens)
- Should be deletable without read-before-delete enforcement
- Are safe to ignore in most operations

**Exempt Patterns** (from read-before-delete):
- `__pycache__` - Python bytecode cache directories
- `.pyc`, `.pyo` - Python bytecode files
- `.pytest_cache`, `.mypy_cache`, `.ruff_cache` - Tool caches
- `.coverage`, `*.egg-info` - Build/test artifacts
- `.tox`, `.nox` - Test environment managers
- `node_modules`, `.next`, `.nuxt` - JavaScript build outputs
- `dist`, `build` - Build directories
- `.DS_Store`, `Thumbs.db` - OS-generated files
- `*.log`, `*.swp`, `*.swo`, `*~` - Editor/log files

**Implementation:**
```python
# In FileOperationTracker._is_auto_generated()
# Checks if file path matches any auto-generated pattern
# Used in can_delete() and can_delete_directory()
```

This prevents permission errors when agents try to clean up after running tests or builds.

## Code Execution Result Guidance

When command execution is enabled, agents are instructed to explain code execution results in their answers via system message guidance.

**Implementation:**
- Location: `massgen/message_templates.py:626-631`
- Adds guidance to agents when `enable_command_execution=True`
- Instructions are injected into filesystem system messages

**Guidance Given to Agents:**
```
**New Answer**: When calling `new_answer`:
- If you executed commands (e.g., running tests), explain the results in your answer (what passed, what failed, what the output shows)
- If you created files, list your cwd and file paths (but do NOT paste full file contents)
- If providing a text response, include your analysis/explanation in the `content` field
```

**Purpose:**
- Ensures agents explain what they learned from running tests/commands
- Makes agent answers more informative and actionable
- Helps users understand what was tested and what the results mean
- Prevents agents from just running tests without explaining the outcome

**Example Agent Behavior:**
Without this guidance:
```
I ran the tests. Here are the files: test.py, main.py
```

With this guidance:
```
I created a factorial function in main.py and wrote comprehensive tests in test.py.
When I ran `pytest test.py`, all 5 tests passed:
- test_factorial_zero: ✓
- test_factorial_positive: ✓
- test_factorial_negative: ✓ (properly raises ValueError)
- test_factorial_large: ✓ (handles n=20)
- test_factorial_one: ✓

The implementation correctly handles edge cases and validates input.
```

## Virtual Environment Support

Commands are executed with automatic `.venv` detection per workspace:

### Auto-Detection (Per-Workspace)
Automatically detects and uses `.venv` directory in each workspace:
```yaml
agent:
  backend:
    enable_mcp_command_line: true
    # No additional config needed - auto-detects .venv
```

**Behavior:**
- Each workspace independently checks for `.venv/` directory in `work_dir`
- Modifies `PATH` to include venv's bin directory
- Sets `VIRTUAL_ENV` environment variable
- Falls back to system environment if no venv found
- **Per-workspace isolation**: Multiple agents with different workspaces = different venvs

**Supported environments:**
- ✅ Standard Python venv (`python -m venv .venv`)
- ✅ uv-created venvs (`uv venv`)
- ✅ poetry venvs (when `.venv` is in workspace)

**Implementation:**
- `_prepare_environment(work_dir: Path)` in `_code_execution_server.py`
- Checks `work_dir/.venv` on each command execution
- Platform-aware: Uses `Scripts/` on Windows, `bin/` on Unix/Mac

## Configuration Examples

### Basic Command Execution (Auto-detect venv)
```yaml
agent:
  backend:
    type: "openai"
    model: "gpt-4o"
    cwd: "workspace"
    enable_mcp_command_line: true
```

### Multi-Agent with Different Workspaces
```yaml
agents:
  - id: "agent_a"
    backend:
      type: "openai"
      model: "gpt-4o"
      cwd: "workspace1"  # Independent .venv
      enable_mcp_command_line: true

  - id: "agent_b"
    backend:
      type: "openai"
      model: "gpt-4o"
      cwd: "workspace2"  # Independent .venv
      enable_mcp_command_line: true
```

### Command Filtering (Whitelist)
**Use `"command.*"` not `"command .*"` to match bare commands**
```yaml
agent:
  backend:
    type: "openai"
    model: "gpt-4o"
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_allowed_commands:
      - "python.*"   # Matches: python, python test.py, python -m pytest
      - "pytest.*"   # Matches: pytest, pytest -v, pytest tests/
      - "pip.*"      # Matches: pip, pip install requests
```

**Important Regex Pattern Note:**
- ✅ Correct: `"pytest.*"` matches `pytest`, `pytest -v`, `pytest tests/`
- ❌ Wrong: `"pytest .*"` only matches `pytest ` with space (misses bare `pytest`)
- Patterns use `re.match()` which matches from start of string
- `.*` matches zero or more of any character

### Command Filtering (Blacklist)
**Use `"command.*"` not `"command .*"` to match bare commands**
```yaml
agent:
  backend:
    type: "gemini"
    model: "gemini-2.5-pro"
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_blocked_commands:
      - "python.*"   # Blocks all Python commands
      - "pytest.*"   # Blocks all pytest commands
      - "pip.*"      # Blocks all pip commands
      - "rm.*"       # Blocks rm (already blocked by AG2 sanitization)
```

## Usage Examples

Once implemented, agents can execute commands:

```
# Run Python script
execute_command("python test_suite.py")

# Run tests
execute_command("pytest tests/ -v")

# Install package and run
execute_command("pip install requests && python scraper.py")

# Build project
execute_command("npm run build")

# Check Python version
execute_command("python --version")
```

## Dependencies

**New Dependencies:**
- None required for local mode (AG2 already in pyproject.toml)
- For Docker mode: `docker` Python library (optional)
  ```toml
  docker = ">=7.0.0"  # Optional dependency
  ```

**Existing Dependencies:**
- `ag2>=0.9.10`: ✅ Already in pyproject.toml
- `fastmcp>=2.12.3`: ✅ Already in pyproject.toml

## Testing Strategy

### Unit Tests

**Code Execution Tests** (`massgen/tests/test_code_execution.py` - 350 lines, 11 test classes):
```python
class TestCodeExecutionBasics:
    """Test basic command execution functionality"""

class TestPathValidation:
    """Test path validation and security"""

class TestCommandSanitization:
    """Test dangerous command blocking (AG2-inspired)"""

class TestOutputHandling:
    """Test output capture and size limits"""

class TestVirtualEnvironment:
    """Test .venv auto-detection"""

class TestAutoGeneratedFiles:
    """Test __pycache__, .pyc deletion without read"""
```

**Permission Validation Tests** (`massgen/tests/test_path_permission_manager.py` - 93 new lines):
```python
def test_validate_execute_command_tool():
    """Test command tool validation for execute_command"""
    # Tests dangerous patterns blocking
    # Tests safe command allowance
    # Tests write operations to readonly paths

async def test_pre_tool_use_hook():
    """Test PreToolUse hook integration"""
    # Tests execute_command goes through hooks
    # Tests dangerous commands blocked
    # Tests readonly path enforcement
```

## Success Criteria

- ✅ All backends can execute commands via MCP
- ✅ Local execution mode works reliably
- ✅ PathPermissionManager integration enforces workspace restrictions
- ✅ Command filtering (whitelist/blacklist) works with regex patterns
- ✅ Timeout enforcement works correctly
- ✅ Per-workspace virtual environment isolation
- ✅ Unit tests achieve >80% coverage (350 lines execution tests + 93 lines permission tests)
- ✅ Documentation is complete
- ⏳ Production testing with OpenAI, Gemini, Grok backends

## Future Enhancements

### 1. Docker Isolation (Issue #304)
Full container isolation for enhanced security:

**Goals:**
- Place workspaces within Docker containers
- Read-only mounts for context paths
- Network isolation (optional)
- Memory and CPU limits
- Auto-cleanup after execution

**Benefits:**
- Stronger isolation than local execution
- Pre-installed packages in base image (fast startup)
- Fresh environment each turn (clean state)
- Version-controlled dependencies (Dockerfile in git)

**Architecture:**
```
FilesystemManager → DockerManager → Docker API → Container
                      ↓
               MCP servers run inside container
                      ↓
               Workspace mounted as volume
```

### 2. Custom Docker Image Workflows
Make it easy for users to bring their own packages and containers:

**Goals:**
- Dockerfile templates for common stacks (data science, web dev, ML/AI)
- Build scripts for easy custom image creation
- Documentation for bringing your own containers
- Example custom Dockerfiles

**Example workflow:**
1. User creates `Dockerfile.custom` with their dependencies
2. Builds once: `docker build -t my-custom-image .`
3. References in config: `docker_image: "my-custom-image"`
4. Agents get those packages instantly

### 3. Additional Testing & Enhancements
- Production testing with OpenAI, Gemini, Grok backends
- Performance benchmarking and optimization
- Advanced resource monitoring and limits
- Windows support testing
- Multi-architecture support (ARM)

## References

- [AG2 Code Execution](https://ag2ai.github.io/ag2/docs/topics/code-execution)
- [AG2 LocalCommandLineCodeExecutor](https://ag2ai.github.io/ag2/docs/reference/coding/local_commandline_code_executor)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- Issue #295: https://github.com/Leezekun/MassGen/issues/295
- PathPermissionManager: `massgen/filesystem_manager/_path_permission_manager.py`
