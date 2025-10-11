# Command Execution Examples

These configurations demonstrate how to enable command line execution for any backend via MCP.

## Basic Examples

### 1. Basic Command Execution
**File:** `basic_command_execution.yaml`

Simple command execution with auto-detection of `.venv` directory in workspace.

```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/code-execution/basic_command_execution.yaml \
  "Write a Python function to calculate factorial and test it"
```

## Command Filtering Examples

### 2. Whitelist Filtering
**File:** `command_filtering_whitelist.yaml`

Restrict to Python/testing commands only (python, pytest, pip).

```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/code-execution/command_filtering_whitelist.yaml \
  "Write and test a sorting algorithm"
```

### 3. Blacklist Filtering
**File:** `command_filtering_blacklist.yaml`

Block additional commands beyond default safety (all rm, network commands, git push).

```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/code-execution/command_filtering_blacklist.yaml \
  "Create a simple data analysis script"
```

## Virtual Environment Examples

### 4. UV Package Management
**File:** `uv_package_management.yaml`

Automatically prefix all commands with `uv run` for uv-managed projects.

**Note:** Agents should use normal commands like `python script.py` - the system automatically adds `uv run` prefix.

```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/code-execution/uv_package_management.yaml \
  "Build a CLI tool with dependencies"
```

### 5. Conda Environment
**File:** `conda_environment.yaml`

Run all commands in a specified conda environment.

```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/code-execution/conda_environment.yaml \
  "Analyze data with pandas"
```

## Multi-Agent Examples

### 6. Different Permissions
**File:** `multi_agent_different_permissions.yaml`

Multiple agents with different command execution capabilities:
- **Coder:** Full command access
- **Reviewer:** Read-only commands (cat, ls, grep, python -c)

```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/code-execution/multi_agent_different_permissions.yaml \
  "Write a web scraper and review it"
```

## Configuration Options

### Basic Setup
```yaml
agent:
  backend:
    cwd: "workspace"  # Required for filesystem + command execution
    enable_mcp_command_line: true

orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"
```

**Note:** The `orchestrator` section is required when using `cwd` (filesystem support).

### Command Filtering
```yaml
agent:
  backend:
    enable_mcp_command_line: true
    # Whitelist (only these patterns allowed)
    command_line_allowed_commands:
      - "python .*"
      - "pytest .*"
    # Blacklist (these patterns blocked)
    command_line_blocked_commands:
      - "rm .*"
      - "sudo .*"
```

### Virtual Environment
```yaml
agent:
  backend:
    enable_mcp_command_line: true
    # Option 1: Command prefix (uv, conda, poetry)
    command_execution_prefix: "uv run"
    # Note: Agents use normal commands, prefix is added automatically

    # Option 2: Custom venv path
    command_execution_venv_path: "/path/to/.venv"
    # Note: Modifies PATH environment variable

    # Option 3: Auto-detect (default) - no config needed
    # Automatically detects .venv in workspace
```

## Default Safety

All command execution includes these safety checks by default (inspired by AG2):
- ❌ `rm -rf /` - Root deletion blocked
- ❌ `dd` - Disk write blocked
- ❌ Fork bombs - Process bombs blocked
- ❌ `/dev` writes - Direct device writes blocked
- ❌ `/dev/null` moves - File destruction blocked
- ❌ `sudo` - Privilege escalation blocked
- ❌ `su` - User switching blocked
- ❌ `chmod` - Permission changes blocked
- ❌ `chown` - Ownership changes blocked

User-configured whitelist/blacklist filters apply **in addition to** these defaults.

## See Also

- Design document: `/docs/dev_notes/CODE_EXECUTION_DESIGN.md`
- Tests: `/massgen/tests/test_code_execution.py`
- Server implementation: `/massgen/filesystem_manager/_code_execution_server.py`
