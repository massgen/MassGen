# MassGen Docker Runtime Environment

This directory contains the Docker configuration for MassGen's isolated MCP server runtime.

## Overview

The Docker runtime provides strong filesystem isolation for agents by running ALL MCP servers (filesystem, workspace_tools, command_line) inside a Docker container. This prevents agents from accessing files outside their designated workspaces.

## Building the Image

From the repository root:

```bash
docker build -t massgen/mcp-runtime:latest -f massgen/docker/Dockerfile .
```

Or with a specific version tag:

```bash
docker build -t massgen/mcp-runtime:1.0.0 -f massgen/docker/Dockerfile .
```

## Image Contents

- **Base**: Python 3.11-slim
- **System Tools**: git, curl, nodejs (v20 LTS), npm
- **Python Packages**:
  - fastmcp (MCP server framework)
  - ag2 (code execution utilities)
  - pytest (testing framework)
  - requests, numpy, pandas (common data tools)
- **Security**: Runs as non-root user (`massgen`)
- **Directories**:
  - `/workspace` - Agent's working directory (mounted from host)
  - `/context` - Context paths (mounted from host)
  - `/temp_workspaces` - Shared reference workspace (mounted from host)
  - `/app/servers` - MCP server implementations

## Usage

### Basic Configuration

Enable Docker isolation in your agent configuration:

```yaml
agent:
  backend:
    cwd: "workspace"
    enable_docker_isolation: true
    enable_mcp_command_line: true
```

By default, when `enable_docker_isolation: true`, the `docker_run_mcp_inside` parameter defaults to `false`, meaning **MCP servers run on the host while commands execute in Docker** for good isolation without exposing MCP server code.

### Docker Isolation Modes

MassGen supports two Docker isolation modes:

#### Mode 1: Commands-Only in Docker (Default, Recommended)

**Configuration:**
```yaml
agent:
  backend:
    enable_docker_isolation: true
    docker_run_mcp_inside: false  # Default - MCP on host, commands in Docker
```

**How it works:**
- MCP servers run on the host machine
- Only command execution happens inside the container
- Good isolation for code execution without exposing MCP server code
- MCP server source code stays outside the container

**When to use:** Default choice for most use cases - provides strong isolation for agent code execution while keeping the MCP server implementation secure

**Why this is the default:** Running MCP servers inside the container would require mounting the massgen codebase, which would expose it to the agent and break isolation.

#### Mode 2: Full MCP-in-Docker (Experimental)

**Configuration:**
```yaml
agent:
  backend:
    enable_docker_isolation: true
    docker_run_mcp_inside: true  # Explicitly enable MCP-in-Docker
```

**How it works:**
- All MCP servers (filesystem, workspace_tools, command_line) run inside the container
- MCP server processes are launched using `docker exec`
- Requires mounting massgen package into container

**When to use:** Development, debugging, or testing only

**⚠️ Warning:** This mode mounts the massgen codebase into the container at `/app/massgen`, which means the agent can potentially access MCP server source code. This breaks isolation boundaries. For production use with full isolation, build a custom Docker image with massgen pre-installed instead.

**Future Plans:** We plan to support full MCP-in-Docker mode without breaking isolation by:
- Using the [official MCP filesystem server's Docker support](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
- Implementing similar containerized solutions for our custom MCP servers (workspace_tools, command_line)
- This will provide an extra layer of security to ensure files aren't written or read outside designated paths

### Advanced Configuration

```yaml
agent:
  backend:
    cwd: "workspace"
    enable_docker_isolation: true
    docker_run_mcp_inside: true  # Run MCP servers inside Docker (default)
    docker_image: "massgen/mcp-runtime:latest"
    docker_network_mode: "none"  # none/bridge/host
    docker_memory_limit: "2g"
    docker_cpu_limit: "2.0"
    enable_mcp_command_line: true
```

### Custom Docker Images

To create a custom image with additional tools:

```dockerfile
FROM massgen/mcp-runtime:latest

# Install additional system packages
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install additional Python packages
USER massgen
RUN pip install --no-cache-dir \
    sqlalchemy \
    psycopg2-binary

# Return to workspace
WORKDIR /workspace
```

Build your custom image:

```bash
docker build -t my-custom-massgen:latest -f Dockerfile.custom .
```

Then reference it in your config:

```yaml
agent:
  backend:
    enable_docker_isolation: true
    docker_image: "my-custom-massgen:latest"
```

## Security Features

1. **Filesystem Isolation**: Agents can only access mounted volumes
2. **Network Isolation**: Default network mode is "none" (no network access)
3. **Resource Limits**: Configurable CPU and memory limits
4. **Non-root Execution**: MCP servers run as `massgen` user (UID 1000)
5. **Command Sanitization**: Dangerous commands blocked (rm -rf /, sudo, etc.)

## Troubleshooting

### Container Name Conflict

If you see an error like:
```
Error: Conflict. The container name "/massgen-docker_agent" is already in use
```

This happens when a previous container wasn't cleaned up properly.

**Automatic handling:** The latest version automatically removes conflicting containers. If you still see this error, manually clean up:

```bash
# Remove specific container
docker rm -f massgen-docker_agent

# Or remove all massgen containers
docker ps -a | grep massgen | awk '{print $1}' | xargs docker rm -f
```

### Container Won't Start

Check Docker is running:
```bash
docker ps
```

Check image exists:
```bash
docker images | grep massgen
```

### Permission Errors

Ensure workspace directories have correct permissions:
```bash
chmod -R 755 workspace
```

### Network Connectivity Issues

If agents need network access, change network mode:
```yaml
docker_network_mode: "bridge"
```

### Performance Issues

Increase resource limits:
```yaml
docker_memory_limit: "4g"
docker_cpu_limit: "4.0"
```

## Development

### Testing Locally

Run a test container interactively:

```bash
docker run -it --rm \
  -v $(pwd)/workspace:/workspace \
  massgen/mcp-runtime:latest \
  /bin/bash
```

### Debugging MCP Servers

View MCP server logs from within container:

```bash
docker exec -it <container_id> /bin/bash
ps aux | grep fastmcp
```

## Maintenance

### Updating the Image

After modifying the Dockerfile, rebuild:

```bash
docker build -t massgen/mcp-runtime:latest -f massgen/docker/Dockerfile .
```

Clean up old images:

```bash
docker image prune -f
```

### Container Cleanup

MassGen automatically cleans up containers on agent shutdown. Manual cleanup if needed:

```bash
# List all containers
docker ps -a | grep massgen

# Remove specific container
docker rm -f <container_id>

# Remove all stopped containers
docker container prune -f
```

## Logging and Monitoring

MassGen provides detailed logging for all Docker operations. See [LOGGING.md](./LOGGING.md) for:
- What logs you'll see during container lifecycle
- Helpful Docker commands shown in debug mode
- Error scenarios and how to diagnose them
- Log level configuration

Quick summary:
```
🐳 [Docker] Creating container for agent 'docker_agent'
    Image: massgen/mcp-runtime:latest
    Network: none
    Memory limit: 2g
    Volume mounts:
      /workspace ← /path/to/workspace (rw)
✅ [Docker] Container created successfully
    Container ID: a1b2c3d4e5f6
    Status: running
```

## References

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [AG2 Code Execution](https://docs.ag2.ai/docs/topics/code-execution/)
- [MassGen Docker Logging](./LOGGING.md) - Detailed logging documentation
