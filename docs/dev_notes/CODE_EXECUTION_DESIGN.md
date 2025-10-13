# Code Execution System Design

**Issues:** #295, #304
**Author:** MassGen Team
**Date:** 2025-10-11
**Status:** In Progress

## Overview

This design doc covers the implementation of code execution for all backends via a single MCP command execution tool, with optional Docker-based isolation for improved security.

## Problem Statement

Currently, only Claude Code backend can execute bash commands. This limitation prevents other backends (OpenAI, Gemini, Grok, etc.) from:
- Running unit tests they write
- Executing code for self-improvement
- Performing filesystem operations beyond basic read/write

Additionally, the current filesystem permission system uses pattern-matching which can be circumvented. We need stronger isolation via Docker containers.

## Goals

### Primary Goals (Issue #295)
1. Enable code execution for all backends through a single MCP tool
2. Support multiple execution modes: local and Docker
3. Use AG2's code execution infrastructure as foundation

### Primary Goals (Issue #304)
1. Place workspaces within Docker containers for isolation
2. Restrict access to prevent information leaking
3. Ensure agents cannot access files outside designated workspaces

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Backend (Any)                         │
│                   (OpenAI, Claude, Gemini, etc.)            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ MCP Protocol
                         │
┌────────────────────────┴────────────────────────────────────┐
│                   Code Execution MCP Server                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Single Tool:                                         │  │
│  │  - execute_command(command, timeout, work_dir)       │  │
│  │                                                        │  │
│  │  Examples:                                            │  │
│  │    execute_command("python test.py")                 │  │
│  │    execute_command("npm test")                       │  │
│  │    execute_command("pytest tests/")                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────┴──────────────────────────────┐ │
│  │       Executor Manager (Mode Selection)               │ │
│  │  - Local Mode: LocalCommandLineCodeExecutor (AG2)    │ │
│  │  - Docker Mode: DockerCommandLineCodeExecutor (AG2)  │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Execution
                         │
┌────────────────────────┴────────────────────────────────────┐
│              Execution Environment                           │
│  ┌──────────────────┐         ┌──────────────────────────┐ │
│  │  Local Shell     │   OR    │  Docker Container        │ │
│  │  - Direct exec   │         │  - Isolated environment  │ │
│  │  - Fast startup  │         │  - Volume mounts         │ │
│  │  - Less secure   │         │  - Network restrictions  │ │
│  └──────────────────┘         │  - Resource limits       │ │
│                                └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Docker Integration Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    FilesystemManager                          │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Docker Workspace Manager (NEW)                        │ │
│  │  - Create/manage Docker containers                     │ │
│  │  - Mount workspaces as volumes                         │ │
│  │  - Mount context paths (read-only)                     │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Docker API
                         │
┌────────────────────────┴────────────────────────────────────┐
│                    Docker Container                          │
│  Volume Mounts:                                             │
│  /workspace           (read-write, agent workspace)         │
│  /context/*           (read-only, context paths)            │
│  /temp_workspaces/*   (read-only, other agents' outputs)    │
│                                                              │
│  Environment:                                                │
│  - HOME=/workspace                                           │
│  - PATH=/usr/local/bin:/usr/bin:/bin                        │
│  - No network access (optional)                              │
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
        "--mode",
        type=str,
        default="local",
        choices=["local", "docker"],
        help="Execution mode: local or docker"
    )
    parser.add_argument(
        "--allowed-paths",
        type=str,
        nargs="*",
        default=[],
        help="List of allowed base paths for execution"
    )
    parser.add_argument(
        "--docker-image",
        type=str,
        default="python:3.11-slim",
        help="Docker image to use (docker mode only)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Default timeout in seconds"
    )
    args = parser.parse_args()

    mcp = fastmcp.FastMCP("Code Execution")

    # Initialize executor manager based on mode
    if args.mode == "docker":
        from autogen.coding import DockerCommandLineCodeExecutor
        executor = DockerCommandLineCodeExecutor(
            image=args.docker_image,
            timeout=args.timeout,
            work_dir=Path.cwd()
        )
    else:
        from autogen.coding import LocalCommandLineCodeExecutor
        executor = LocalCommandLineCodeExecutor(
            timeout=args.timeout,
            work_dir=Path.cwd()
        )

    mcp.executor = executor
    mcp.allowed_paths = [Path(p).resolve() for p in args.allowed_paths]

    @mcp.tool()
    def execute_command(
        command: str,
        timeout: Optional[int] = None,
        work_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        # Implementation here
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
    command_execution_mode: str = "local",  # "local" or "docker"
    command_docker_image: str = "python:3.11-slim",
):
    # ... existing initialization ...

    self.enable_mcp_command_line = enable_mcp_command_line
    self.command_execution_mode = command_execution_mode
    self.command_docker_image = command_docker_image
```

**New Method:**

```python
def get_command_line_mcp_config(self) -> Dict[str, Any]:
    """
    Generate command line execution MCP server configuration.

    Returns:
        Dictionary with MCP server configuration for command execution
        (supports bash on Unix/Mac, cmd/PowerShell on Windows)
    """
    script_path = Path(__file__).parent / "_code_execution_server.py"

    config = {
        "name": "command_line",
        "type": "stdio",
        "command": "fastmcp",
        "args": [
            "run",
            f"{script_path}:create_server",
            "--",
            "--mode", self.command_execution_mode,
            "--allowed-paths"
        ] + self.path_permission_manager.get_mcp_filesystem_paths(),
        "cwd": str(self.cwd),
    }

    if self.command_execution_mode == "docker":
        config["args"].extend(["--docker-image", self.command_docker_image])

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

**Local Mode:**
- Commands execute in workspace directory
- Timeout enforcement prevents infinite loops
- Output size limits prevent memory exhaustion
- Uses existing PathPermissionManager restrictions

**Docker Mode:**
- Full container isolation
- Read-only mounts for context paths
- Optional network isolation
- Memory and CPU limits (configurable)
- Auto-cleanup after execution

**Common Security:**
- AG2-inspired dangerous command sanitization (always applied):
  - `rm -rf /` - Root deletion blocked
  - `dd` - Disk write blocked
  - Fork bombs - Process bombs blocked
  - `/dev` writes - Direct device writes blocked
  - `/dev/null` moves - File destruction blocked
  - `sudo` - Privilege escalation blocked
  - `su` - User switching blocked
  - `chmod` - Permission changes blocked
  - `chown` - Ownership changes blocked
- Working directory must be within allowed paths
- Timeout enforcement prevents infinite loops
- Output size limits prevent memory exhaustion
- Optional user whitelist/blacklist filters (applied after sanitization)

## Implementation Plan

### Phase 1: Local Code Execution (Issue #295)
1. ✅ Explore codebase structure
2. ✅ Create design document
3. ✅ Implement `_code_execution_server.py` with single `execute_command` tool
4. ✅ Add local mode with subprocess (AG2-inspired sanitization)
5. ✅ Integrate with FilesystemManager
6. ✅ Write unit tests (17/18 passing)
7. ✅ Add virtual environment support (auto-detect, prefix, custom path)
8. ✅ Add command filtering (whitelist/blacklist)
9. ✅ Create example configurations in `massgen/configs/tools/code-execution/`
10. ⏳ Test with OpenAI, Gemini, Grok backends

### Phase 2: Docker Support (Issue #304)
1. ✅ Create Dockerfile for MCP runtime environment (massgen/docker/)
2. ✅ Implement DockerManager class for container lifecycle (_docker_manager.py)
3. ✅ Integrate Docker support into FilesystemManager (5 new parameters)
4. ✅ Wire Docker parameters through backend (base.py, API params handler)
5. ✅ Add runtime-aware system message integration
6. ✅ Create Docker example configurations (3 examples)
7. ✅ Update documentation (README.md, CODE_EXECUTION_DESIGN.md)
8. ✅ Build and test Docker image (massgen/mcp-runtime:latest, 990MB)
9. ✅ Add integration tests for Docker mode (9/9 tests passing)
10. ✅ Add Docker container log saving for debugging
11. ⏳ Test with real backends (OpenAI, Gemini)

### Phase 3: Polish & Documentation
1. ✅ Auto-generated file exclusions (pycache, .pyc, etc.)
2. Error handling and edge cases
3. Update user documentation
4. Add example configurations
5. Performance testing

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

## Docker Container Log Saving

When Docker isolation is enabled, container logs are automatically saved during cleanup for debugging purposes.

**Log Location:**
```
<log_session_dir>/<agent_id>/docker_container.log
```

**What's Captured:**
- Container stdout/stderr output
- Timestamps for all log entries
- All commands executed within the container
- Container lifecycle events (start, stop, errors)

**Implementation:**
- `DockerManager.save_container_logs()` (massgen/filesystem_manager/_docker_manager.py:349-371)
  - Retrieves logs from Docker container using `container.logs(stdout=True, stderr=True, timestamps=True)`
  - Writes logs to specified file path
  - Creates parent directories if needed

- `FilesystemManager.cleanup()` (massgen/filesystem_manager/_filesystem_manager.py:858-875)
  - Constructs log path from log session directory
  - Passes log path to `docker_manager.cleanup(agent_id, save_logs_to=log_path)`
  - Automatically saves logs before stopping and removing containers

**When Cleanup is Called:**
Cleanup is explicitly called in two places:
- **CLI exit** (cli.py:1406-1414): Finally block ensures cleanup on normal exit, error, or Ctrl+C
- **Interactive mode agent recreation** (cli.py:1023-1029): Cleanup old agents before creating new ones

**Usage:**
No configuration needed - logs are automatically saved when:
- Agent execution completes normally
- Agent execution is interrupted (Ctrl+C)
- Cleanup is triggered manually
- CLI exits for any reason

**User-Facing Feedback:**
When cleanup happens, users see: `🧹 Cleaning up Docker container for <agent_id>...`

This message explains the brief delay before returning to the terminal, so users know the system is still working.

**Debugging Workflow:**
1. Run agent with Docker isolation enabled
2. Check logs after execution: `cat massgen_logs/<session>/coder/docker_container.log`
3. See all commands executed and their outputs inside the container

This feature is essential for understanding what happened inside isolated containers, especially when debugging command execution failures or unexpected behavior.

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

Commands can be executed in different virtual environments using three approaches:

### 1. Auto-Detection (Default)
Automatically detects and uses `.venv` directory in the workspace:
```yaml
agent:
  backend:
    enable_mcp_command_line: true
    # No additional config needed - auto-detects .venv
```

**Behavior:**
- Checks for `.venv/` directory in `work_dir`
- Modifies `PATH` to include venv's bin directory
- Sets `VIRTUAL_ENV` environment variable
- Falls back to system environment if no venv found

**Supported environments:**
- ✅ Standard Python venv
- ✅ uv-created venvs
- ✅ poetry venvs

### 2. Command Prefix
Prepends commands with a wrapper (for uv, conda, poetry):
```yaml
agent:
  backend:
    enable_mcp_command_line: true
    command_execution_prefix: "uv run"  # or "conda run -n myenv", "poetry run"
```

**Behavior:**
- All commands prefixed: `uv run python test.py`
- Most flexible - works with any command wrapper
- Handles complex environment managers like conda

### 3. Custom Venv Path
Explicitly specify venv location:
```yaml
agent:
  backend:
    enable_mcp_command_line: true
    command_execution_venv_path: "/path/to/custom/.venv"
```

**Behavior:**
- Uses specified venv path instead of auto-detecting
- Modifies `PATH` like auto-detection

### Priority Order
```
1. command_execution_prefix (if set) → prepend to commands
2. command_execution_venv_path (if set) → modify PATH
3. Auto-detect .venv in work_dir → modify PATH
4. Use system environment
```

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

### Using uv for Package Management
```yaml
agent:
  backend:
    type: "openai"
    model: "gpt-4o"
    cwd: "workspace"
    enable_mcp_command_line: true
    command_execution_prefix: "uv run"
```

### Using Conda Environment
```yaml
agent:
  backend:
    type: "openai"
    model: "gpt-4o"
    cwd: "workspace"
    enable_mcp_command_line: true
    command_execution_prefix: "conda run -n myenv"
```

### Command Filtering (Whitelist)
```yaml
agent:
  backend:
    type: "openai"
    model: "gpt-4o"
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_allowed_commands:
      - "python .*"
      - "pytest .*"
```

### Command Filtering (Blacklist)
```yaml
agent:
  backend:
    type: "gemini"
    model: "gemini-2.5-pro"
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_blocked_commands:
      - "rm .*"
      - "sudo .*"
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

### Unit Tests (`massgen/tests/test_code_execution.py`)
```python
def test_execute_command_simple():
    """Test basic command execution"""

def test_execute_command_timeout():
    """Test timeout enforcement"""

def test_execute_command_working_directory():
    """Test working directory handling"""

def test_execute_command_permission_validation():
    """Test path permission checks"""

@pytest.mark.skipif(not has_docker(), reason="Docker not available")
def test_execute_command_docker_mode():
    """Test Docker execution mode"""
```

## Success Criteria

- ✅ All backends can execute commands via MCP
- ✅ Both local and Docker modes work
- ✅ Timeout enforcement works correctly
- ✅ Docker isolation prevents access outside workspace
- ✅ Unit tests achieve >80% coverage
- ✅ Documentation is complete

## Future Enhancements

### Custom Docker Image Workflows
Make it easy for users to bring their own packages and containers:

**Goals:**
- Dockerfile templates for common stacks (data science, web dev, ML/AI)
- Build scripts for easy custom image creation
- Documentation for bringing your own containers
- Example custom Dockerfiles in `massgen/docker/examples/`

**Benefits:**
- Pre-installed packages in base image (fast startup)
- Fresh venv each turn (clean state, no conflicts)
- Version-controlled dependencies (Dockerfile in git)
- Docker layer caching (efficient builds)

**Example workflow:**
1. User creates `Dockerfile.custom` extending `massgen/mcp-runtime:latest`
2. Adds their common packages (scikit-learn, transformers, etc.)
3. Builds once: `docker build -t my-custom-image .`
4. References in config: `docker_image: "my-custom-image"`
5. Agents get those packages instantly each turn

### Other Future Work

1. **Full MCP-in-Docker without isolation breaking**
   - Use official MCP filesystem server's Docker support
   - Implement containerized custom MCP servers
   - Provide extra layer of security for file operations

2. **Additional Testing**
   - Test with OpenAI, Gemini, Grok backends in production
   - Performance benchmarking (local vs Docker)
   - Stress testing with concurrent agents

3. **Additional Enhancements**
   - Advanced resource monitoring and limits
   - Windows Docker support testing
   - Multi-architecture Docker images (ARM support)

## References

- [AG2 Code Execution](https://ag2ai.github.io/ag2/docs/topics/code-execution)
- [AG2 LocalCommandLineCodeExecutor](https://ag2ai.github.io/ag2/docs/reference/coding/local_commandline_code_executor)
- [AG2 DockerCommandLineCodeExecutor](https://ag2ai.github.io/ag2/docs/reference/coding/docker_commandline_code_executor)
- Issue #295: https://github.com/Leezekun/MassGen/issues/295
- Issue #304: https://github.com/Leezekun/MassGen/issues/304
