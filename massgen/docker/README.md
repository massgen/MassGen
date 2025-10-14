# MassGen Docker Runtime for Code Execution

This directory contains Docker configuration for isolated command execution in MassGen.

## Overview

Docker mode provides strong isolation for command execution by running commands inside persistent containers while keeping MCP servers on the host for security.

**Key Benefits:**
- 🔒 **Isolation:** Commands execute in containers, can't access host filesystem
- 📦 **State Persistence:** Packages stay installed across turns (persistent containers)
- 🚀 **Easy Setup:** Single command to build, simple config to enable
- 🛡️ **Security:** Read-only context mounts, optional network isolation, resource limits
- 🧪 **Clean Environment:** Each agent gets its own isolated container

## Quick Start

### 1. Prerequisites

- **Docker installed and running**
  ```bash
  docker --version  # Should show Docker 20.x or later
  docker ps         # Should connect without errors
  ```

- **Python docker library (optional, for Docker mode)**
  ```bash
  # Install via optional dependency group
  uv pip install -e ".[docker]"

  # Or install directly
  pip install docker>=7.0.0
  ```

### 2. Build the Docker Image

From the repository root:

```bash
bash massgen/docker/build.sh
```

This builds `massgen/mcp-runtime:latest` (~400-500MB).

### 3. Enable in Configuration

**Minimal setup:**
```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"  # This enables Docker mode!
```

**That's it!** Container will be created automatically when orchestration starts.

## Configuration Options

### Basic Docker Mode

```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"
```

### With Resource Limits and Network

```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"

    # Docker configuration
    command_line_docker_image: "massgen/mcp-runtime:latest"  # Default
    command_line_docker_memory_limit: "2g"                   # Limit memory
    command_line_docker_cpu_limit: 4.0                        # Limit CPU cores
    command_line_docker_network_mode: "bridge"               # Enable network
```

### Multi-Agent Docker Execution

```yaml
agents:
  - id: "agent_a"
    backend:
      type: "openai"
      model: "gpt-5-mini"
      cwd: "workspace1"
      enable_mcp_command_line: true
      command_line_execution_mode: "docker"

  - id: "agent_b"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      cwd: "workspace2"
      enable_mcp_command_line: true
      command_line_execution_mode: "docker"
```

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `command_line_execution_mode` | `"local"` | `"local"` or `"docker"` |
| `command_line_docker_image` | `"massgen/mcp-runtime:latest"` | Docker image to use |
| `command_line_docker_memory_limit` | None | Memory limit (e.g., `"2g"`, `"512m"`) |
| `command_line_docker_cpu_limit` | None | CPU cores limit (e.g., `2.0`) |
| `command_line_docker_network_mode` | `"none"` | `"none"`, `"bridge"`, or `"host"` |

## How It Works

### Container Lifecycle

```
Orchestration Start
    ↓
FilesystemManager.setup_orchestration_paths()
    ├── Creates persistent container: massgen-{agent_id}
    ├── Mounts workspace at SAME host path (rw) - path transparency
    ├── Mounts context paths at SAME host paths (ro by default)
    └── Mounts temp_workspace at SAME host path (ro)
    ↓
Agent Turn 1
    ├── execute_command("pip install click")
    └── docker exec massgen-{agent_id} sh -c "pip install click"
    ↓
Agent Turn 2
    ├── execute_command("python -c 'import click; print(click.__version__)'")
    └── docker exec massgen-{agent_id} sh -c "python -c 'import click; print(click.__version__)'"
        (click is available - container persisted!)
    ↓
Orchestration End
    ├── FilesystemManager.cleanup()
    └── Stops and removes container
```

### Key Design Decisions

1. **Persistent Containers**
   - One container per agent for entire orchestration
   - State persists across turns (packages, files, etc.)
   - Destroyed only at orchestration end

2. **MCP Servers on Host**
   - Code execution MCP server runs on host (not in container)
   - Creates own Docker client connection
   - Executes commands via `docker exec`
   - **Why:** Keeps MCP server source code secure, not exposed to agents

3. **Path Transparency (Volume Mounting)**
   - Paths mounted at SAME location as host (Docker invisible to LLM)
   - Workspace: Read-write access to agent's workspace
   - Context paths: Read-only or read-write based on config
   - Temp workspace: Read-only access to other agents' outputs

## Docker Image Details

### Base Image: massgen/mcp-runtime:latest

**Contents:**
- Base: Python 3.11-slim
- System packages: git, curl, build-essential, Node.js 20.x
- Python packages: pytest, requests, numpy, pandas
- User: non-root (massgen, UID 1000)
- Working directory: /workspace

**Size:** ~400-500MB (compressed)

### Custom Images

To add more packages, extend the base image:

```dockerfile
FROM massgen/mcp-runtime:latest

# Install additional system packages
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install additional Python packages
USER massgen
RUN pip install --no-cache-dir sqlalchemy psycopg2-binary

WORKDIR /workspace
```

Build and use:
```bash
docker build -t my-custom-runtime:latest -f Dockerfile.custom .
```

```yaml
command_line_docker_image: "my-custom-runtime:latest"
```

## Security Features

### Filesystem Isolation
- Containers can only access mounted volumes
- Workspace: Agent's workspace directory only
- Context paths: Read-only by default (configurable per path)
- No access to host filesystem outside mounts

### Network Isolation (Default)
- `network_mode: "none"` - No network access (default, most secure)
- `network_mode: "bridge"` - Internet access enabled
- `network_mode: "host"` - Full host network (use with caution)

### Resource Limits
- Memory limits prevent memory exhaustion attacks
- CPU limits prevent CPU exhaustion attacks
- Enforced at container level by Docker runtime

### Process Isolation
- Commands run as non-root user (massgen, UID 1000)
- Cannot affect host processes
- Cannot access other agent containers

### Combined with Other Security Layers
1. AG2-inspired command sanitization (rm -rf /, sudo, etc.)
2. Command filtering (whitelist/blacklist)
3. Docker container isolation ← **This layer**
4. Volume mount permissions (ro/rw)
5. PathPermissionManager hooks

## Usage Examples

### Example 1: Python Development

```yaml
agent:
  backend:
    model: "gpt-4o-mini"
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"
```

```bash
uv run python -m massgen.cli --config config.yaml "Write and test a sorting algorithm"
```

Agent can:
- Install packages: `pip install numpy`
- Run code: `python sort.py`
- Run tests: `pytest tests/`
- All isolated in container!

### Example 2: With Resource Constraints

```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"
    command_line_docker_memory_limit: "1g"  # Limit memory
    command_line_docker_cpu_limit: 1.0      # Limit to 1 CPU
    command_line_docker_network_mode: "none"  # No network
```

Good for untrusted or resource-intensive tasks.

### Example 3: With Network Access

```yaml
agent:
  backend:
    cwd: "workspace"
    enable_mcp_command_line: true
    command_line_execution_mode: "docker"
    command_line_docker_network_mode: "bridge"  # Enable network
```

```bash
uv run python -m massgen.cli --config config.yaml "Fetch data from an API and analyze it"
```

Agent can make HTTP requests from inside container.

## Troubleshooting

### Error: "Docker is not installed"

**Symptom:** `RuntimeError: Docker Python library not available`

**Solution:**
```bash
pip install docker>=7.0.0
```

### Error: "Failed to connect to Docker"

**Symptom:** `RuntimeError: Failed to connect to Docker: ...`

**Possible causes:**
1. Docker daemon not running
   ```bash
   # Check if Docker is running
   docker ps

   # Start Docker Desktop (Mac/Windows) or daemon (Linux)
   ```

2. Permission issues (Linux)
   ```bash
   # Add user to docker group
   sudo usermod -aG docker $USER
   # Log out and back in for changes to take effect
   ```

3. Custom Docker socket path
   ```bash
   # If Docker uses a non-standard socket path, set DOCKER_HOST
   export DOCKER_HOST=unix:///path/to/your/docker.sock

   # Or for TCP connections
   export DOCKER_HOST=tcp://localhost:2375
   ```

   The Docker SDK auto-detects socket paths, but you can override with `DOCKER_HOST` if needed.

### Error: "Image not found"

**Symptom:** `RuntimeError: Failed to pull Docker image ...`

**Solution:** Build the image locally
```bash
bash massgen/docker/build.sh
```

Or pull if available:
```bash
docker pull massgen/mcp-runtime:latest
```

### Container Name Conflict

**Symptom:** `Error: The container name "/massgen-{agent_id}" is already in use`

**Solution:** This is auto-handled by DockerManager, but if persists:
```bash
# Remove conflicting container
docker rm -f massgen-{agent_id}

# Or remove all massgen containers
docker ps -a | grep massgen | awk '{print $1}' | xargs docker rm -f
```

### Performance Issues

**Symptom:** Commands are slow

**Solutions:**
1. Increase resource limits:
   ```yaml
   command_line_docker_memory_limit: "4g"
   command_line_docker_cpu_limit: 4.0
   ```

2. Use custom image with pre-installed packages (see Custom Images section)

3. Check Docker Desktop resource settings (Mac/Windows)

### Permission Errors in Container

**Symptom:** `Permission denied` when writing files

**Cause:** User ID mismatch between host and container

**Solution:** The container runs as UID 1000. Ensure workspace has correct permissions:
```bash
chmod -R 755 workspace
```

Or build custom image with matching UID:
```dockerfile
RUN useradd -m -u $(id -u) -s /bin/bash massgen
```

## Debugging

### Inspect Running Container

```bash
# List containers
docker ps | grep massgen

# View logs in real-time
docker logs -f massgen-{agent_id}

# Execute interactive shell
docker exec -it massgen-{agent_id} /bin/bash
```

### Check Container Resource Usage

```bash
docker stats massgen-{agent_id}
```

### Manual Container Management

```bash
# Stop container
docker stop massgen-{agent_id}

# Remove container
docker rm massgen-{agent_id}

# Remove all stopped containers
docker container prune -f
```

## Comparison: Local vs Docker Mode

| Aspect | Local Mode | Docker Mode |
|--------|-----------|-------------|
| **Setup** | None required | Docker + image build |
| **Performance** | Fast (direct execution) | Slight overhead (~100-200ms startup) |
| **Isolation** | Pattern-based (circumventable) | Container-based (strong) |
| **Network** | Full host network | Configurable (none/bridge/host) |
| **Resource Limits** | OS-level only | Docker-enforced (memory, CPU) |
| **State Persistence** | Direct filesystem | Container + volumes |
| **Security** | Medium | High |
| **Best For** | Development, trusted code | Production, untrusted code |

## Best Practices

1. **Use Docker mode for untrusted or production workloads**
2. **Set resource limits** to prevent abuse
3. **Use network_mode="none"** unless network is required
4. **Build custom images** for frequently used packages (faster)
5. **Monitor container logs** for debugging
6. **Clean up regularly** if testing (containers auto-cleaned normally)

## Examples Directory

See `massgen/configs/debug/code_execution/` for example configurations:
- `docker_simple.yaml` - Minimal Docker setup
- `docker_with_resource_limits.yaml` - Memory/CPU limits with network access
- `docker_multi_agent.yaml` - Multi-agent execution with Docker isolation
- `docker_verification.yaml` - Verify Docker isolation is working

## References

- [Docker Documentation](https://docs.docker.com/)
- [Docker Python SDK](https://docker-py.readthedocs.io/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- Design Document: `docs/dev_notes/DOCKER_CODE_EXECUTION_DESIGN.md`
- Build Script: `massgen/docker/build.sh`
