# Docker Container Logging

This document shows the Docker container logging that users will see during execution.

## Initialization

When Docker isolation is enabled, you'll see:

```
🐳 [Docker] Client initialized successfully
    Docker version: 27.4.0
    API version: 1.47
```

## Container Creation

When a container is created for an agent:

```
🐳 [Docker] Creating container for agent 'docker_agent'
    Image: massgen/mcp-runtime:latest
    Network: none
    Memory limit: 2g
    CPU limit: 2.0 cores
    Volume mounts:
      /workspace ← /Users/user/project/workspace (rw)
      /temp_workspaces ← /Users/user/project/temp_workspaces (ro)
      /context/shared ← /Users/user/data (ro)
✅ [Docker] Container created successfully
    Container ID: a1b2c3d4e5f6
    Container name: massgen-docker_agent
    Status: running
```

### Debug Mode

With debug logging enabled (`--log-level debug`), you'll also see:

```
💡 [Docker] Inspect container: docker inspect a1b2c3d4e5f6
💡 [Docker] View logs: docker logs a1b2c3d4e5f6
💡 [Docker] Execute commands: docker exec -it a1b2c3d4e5f6 /bin/bash
```

## Container Conflicts

If a container with the same name already exists:

```
🔄 [Docker] Found existing container 'massgen-docker_agent' (id: a1b2c3d4), removing it
```

This is automatic - no user intervention needed!

## Command Execution

When commands run inside containers (debug level):

```
🔧 [Docker] Executing in container a1b2c3d4: python test.py
```

If a command fails:

```
⚠️ [Docker] Command exited with code 1
```

## Container Information

You can request detailed container info programmatically or via logs:

```
📊 [Docker] Container information for agent 'docker_agent':
    ID: a1b2c3d4e5f6
    Name: massgen-docker_agent
    Status: running
    Image: massgen/mcp-runtime:latest
    Network: none
    Memory limit: 2g
    CPU limit: 2.0 cores
```

## Container Cleanup

When containers are stopped and removed:

```
🧹 [Docker] Cleaning up container for agent docker_agent
🛑 [Docker] Stopping container a1b2c3d4 for agent docker_agent
✅ [Docker] Container stopped successfully
🗑️ [Docker] Removing container a1b2c3d4 for agent docker_agent
✅ [Docker] Container removed successfully
```

For multiple containers:

```
🧹 [Docker] Cleaning up 3 container(s)
```

## Error Scenarios

### Docker Daemon Not Running

```
❌ [Docker] Failed to connect to Docker daemon: Cannot connect to Docker daemon
```

**Solution:** Start Docker daemon (`docker ps` to verify)

### Image Not Found

```
❌ [Docker] Failed to create container for agent docker_agent
```

**Solution:** Build the image first:
```bash
docker build -t massgen/mcp-runtime:latest -f massgen/docker/Dockerfile .
```

### Container Creation Failure

```
❌ [Docker] Failed to create container for agent docker_agent: [error details]
```

**Solution:** Check error details, verify Docker has enough resources

## Manual Docker Commands

The logs show helpful commands you can run:

### Inspect Container
```bash
docker inspect <container_id>
```

Shows full container configuration, volumes, network settings.

### View Container Logs
```bash
docker logs <container_id>
```

Shows stdout/stderr from processes inside container.

### Execute Commands
```bash
docker exec -it <container_id> /bin/bash
```

Opens interactive shell inside the container.

### List All Containers
```bash
docker ps -a | grep massgen
```

Shows all MassGen containers (running and stopped).

### Monitor Resource Usage
```bash
docker stats <container_id>
```

Real-time resource usage (CPU, memory, network, I/O).

## Log Levels

Control logging verbosity:

```yaml
# Minimal logging (default)
ui:
  logging_level: "INFO"

# Detailed Docker operations
ui:
  logging_level: "DEBUG"
```

**INFO level:** Container lifecycle events (create, start, stop, remove)
**DEBUG level:** All operations including command execution and helpful Docker commands

## Emoji Legend

- 🐳 Docker initialization/operations
- ✅ Success
- ❌ Error
- ⚠️ Warning (non-critical)
- 🔄 Automatic cleanup/recovery
- 🛑 Stopping
- 🗑️ Removing
- 🧹 Cleanup operation
- 🔧 Command execution
- 💡 Helpful tips (debug mode)
- 📊 Information display
