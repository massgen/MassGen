# Code Execution Configuration Examples

This directory contains example configurations for command execution with various modes and settings.

## Quick Reference

| Config File | Mode | Key Features |
|------------|------|--------------|
| `command_filtering_whitelist.yaml` | Local | Python/pytest only |
| `command_filtering_blacklist.yaml` | Local | Block specific commands |
| `docker_simple.yaml` | Docker | Minimal Docker setup |
| `docker_with_resource_limits.yaml` | Docker | Memory/CPU limits + network |
| `docker_multi_agent.yaml` | Docker | Mixed local/Docker agents |

## Configuration Files

### Local Execution Mode

#### 1. command_filtering_whitelist.yaml
**Purpose:** Restrict to Python and testing commands only

**Run:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/debug/code_execution/command_filtering_whitelist.yaml \
  "Write and test a sorting algorithm"
```

**Key settings:**
```yaml
enable_mcp_command_line: true
command_line_allowed_commands:
  - "python.*"
  - "pytest.*"
  - "pip.*"
```

**Use case:** Python development with test execution only

#### 2. command_filtering_blacklist.yaml
**Purpose:** Block dangerous commands beyond default AG2 sanitization

**Run:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/debug/code_execution/command_filtering_blacklist.yaml \
  "Analyze this codebase"
```

**Key settings:**
```yaml
enable_mcp_command_line: true
command_line_blocked_commands:
  - "rm.*"
  - "curl.*"
  - "wget.*"
```

**Use case:** General development with extra safety

### Docker Execution Mode

**Prerequisites:**
1. Docker installed and running: `docker ps`
2. Docker image built: `bash massgen/docker/build.sh`
3. Optional: Python docker library: `pip install docker>=7.0.0`

#### 3. docker_simple.yaml
**Purpose:** Minimal Docker isolation setup

**Run:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/debug/code_execution/docker_simple.yaml \
  "Write a factorial function and test it"
```

**Key settings:**
```yaml
enable_mcp_command_line: true
command_line_execution_mode: "docker"
```

**What happens:**
- Container `massgen-docker_agent` created at start
- Commands execute via `docker exec` in isolated container
- Packages persist across turns (e.g., `pip install pytest` stays installed)
- Container destroyed at end

**Use case:** Basic Docker isolation for untrusted code

#### 4. docker_with_resource_limits.yaml
**Purpose:** Docker isolation with resource constraints and network access

**Run:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/debug/code_execution/docker_with_resource_limits.yaml \
  "Fetch data from an API and analyze it"
```

**Key settings:**
```yaml
command_line_execution_mode: "docker"
command_line_docker_memory_limit: "2g"       # Limit memory to 2GB
command_line_docker_cpu_limit: 2.0           # Limit to 2 CPU cores
command_line_docker_network_mode: "bridge"   # Enable network access
```

**Use case:** Resource-constrained tasks with network access

#### 5. docker_multi_agent.yaml
**Purpose:** Multiple agents with different execution modes

**Run:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/debug/code_execution/docker_multi_agent.yaml
```

**Key settings:**
```yaml
agents:
  - id: "trusted_local_agent"
    backend:
      command_line_execution_mode: "local"  # Fast, no isolation

  - id: "untrusted_docker_agent"
    backend:
      command_line_execution_mode: "docker"  # Isolated
      command_line_docker_network_mode: "none"
      command_line_docker_memory_limit: "1g"
```

**Use case:** Mixed trust levels, different security requirements

## Configuration Parameters Reference

### Basic Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `cwd` | Yes | - | Workspace directory |
| `enable_mcp_command_line` | Yes | `false` | Enable command execution |
| `command_line_execution_mode` | No | `"local"` | `"local"` or `"docker"` |

### Command Filtering

| Parameter | Type | Description |
|-----------|------|-------------|
| `command_line_allowed_commands` | List[str] | Whitelist regex patterns |
| `command_line_blocked_commands` | List[str] | Blacklist regex patterns |

**Pattern syntax:**
- Use `re.match()` - patterns match from start
- ✅ Correct: `"python.*"` matches `python`, `python test.py`
- ❌ Wrong: `"python .*"` only matches `python ` with space

**Examples:**
```yaml
command_line_allowed_commands:
  - "python.*"   # All Python commands
  - "pytest.*"   # All pytest commands
  - "pip.*"      # All pip commands
```

### Docker Parameters (when mode="docker")

| Parameter | Default | Description |
|-----------|---------|-------------|
| `command_line_docker_image` | `massgen/mcp-runtime:latest` | Docker image |
| `command_line_docker_memory_limit` | None | Memory limit (e.g., `"2g"`) |
| `command_line_docker_cpu_limit` | None | CPU cores (e.g., `2.0`) |
| `command_line_docker_network_mode` | `"none"` | `"none"`, `"bridge"`, `"host"` |

## Security Layers

All modes include multiple security layers:

### Layer 1: AG2-Inspired Sanitization (Always)
- Blocks: `rm -rf /`, `dd`, `sudo`, `su`, `chmod`, `chown`
- Blocks: Fork bombs, `/dev` writes
- Cannot be disabled

### Layer 2: Command Filtering (Optional)
- **Whitelist:** Only allow specific patterns
- **Blacklist:** Block specific patterns
- Applied after AG2 sanitization

### Layer 3: Docker Isolation (Docker mode only)
- Commands run in isolated container
- Volume-mounted filesystem access only
- Configurable network isolation
- Resource limits enforced

### Layer 4: PathPermissionManager (Always)
- Workspace confinement
- Context path permission enforcement
- Read-before-delete policy

## Common Use Cases

### 1. Python Development (Local)
```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
```

**Agent can:**
- Install packages: `pip install requests`
- Run scripts: `python app.py`
- Run tests: `pytest tests/`

### 2. Untrusted Code Execution (Docker)
```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"
    command_line_docker_network_mode: "none"  # No network
```

**Security:**
- Commands isolated in container
- No network access
- Can't affect host system

### 3. API Data Fetching (Docker + Network)
```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"
    command_line_docker_network_mode: "bridge"  # Enable network
```

**Agent can:**
- Make HTTP requests
- Fetch external data
- Still isolated in container

### 4. Resource-Constrained Tasks (Docker + Limits)
```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"
    command_line_docker_memory_limit: "1g"
    command_line_docker_cpu_limit: 1.0
```

**Benefits:**
- Prevents memory exhaustion
- Prevents CPU monopolization
- Good for untrusted/experimental code

## Troubleshooting

### "Command not in allowed list"
**Problem:** Whitelist is too restrictive

**Solution:** Add pattern to allowed list
```yaml
command_line_allowed_commands:
  - "python.*"
  - "node.*"  # Add this
```

### "Docker is not installed"
**Problem:** Docker not available

**Solution:**
```bash
# Install Docker
# Then build image
bash massgen/docker/build.sh
```

### "Permission denied" in Docker
**Problem:** File permissions mismatch

**Solution:**
```bash
chmod -R 755 workspace
```

### "pytest not found" (Docker mode)
**Problem:** Package not installed in container

**Solution:** Agent needs to install first
```
Agent Turn 1: pip install pytest
Agent Turn 2: pytest tests/  # Now works!
```

Container persists, so packages stay installed.

## Tips and Best Practices

1. **Start with local mode** for development (faster)
2. **Use Docker mode** for untrusted code or production
3. **Set resource limits** when using Docker mode
4. **Use whitelist** for maximum security
5. **Use blacklist** for additional safety on top of AG2
6. **Keep network disabled** unless needed (`mode: "none"`)
7. **Build custom Docker images** for frequently used packages

## Examples of Agent Behavior

### Without Command Execution
```
Agent: I've written test.py. I cannot run it.
```

### With Local Mode
```
Agent: I wrote test.py and ran pytest:
✓ test_add passed
✓ test_subtract passed
All tests passed!
```

### With Docker Mode
```
Agent: I installed pytest in the container,
wrote test.py, and ran the tests:
✓ test_factorial_zero passed
✓ test_factorial_positive passed
All 5 tests passed! The implementation handles edge cases correctly.
```

## See Also

- **Design Document:** `docs/dev_notes/CODE_EXECUTION_DESIGN.md`
- **Docker Design:** `docs/dev_notes/DOCKER_CODE_EXECUTION_DESIGN.md`
- **Docker Setup:** `massgen/docker/README.md`
- **Tests:** `massgen/tests/test_code_execution.py`

## Quick Command Reference

```bash
# Run with local mode
uv run python -m massgen.cli --config <config.yaml> "Your prompt"

# Build Docker image (once)
bash massgen/docker/build.sh

# Run with Docker mode
uv run python -m massgen.cli --config <docker_config.yaml> "Your prompt"

# View Docker container logs (after run)
cat massgen_logs/<session_id>/<agent_id>/docker_container.log

# List all config examples
ls massgen/configs/debug/code_execution/
```
