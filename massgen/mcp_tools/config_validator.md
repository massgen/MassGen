# MCP Configuration Validator

The MCP Configuration Validator provides comprehensive validation for MCP (Model Context Protocol) server configurations, ensuring security, correctness, and consistency across your MassGen setup. It integrates with the security module to enforce safe execution environments and validates configuration structure at multiple levels.

## Overview

The `MCPConfigValidator` class serves as the central validation system for MCP configurations in MassGen. It performs three key functions:

1. **Individual Server Validation** - Validates single MCP server configurations with security checks
2. **Backend-Level Validation** - Validates MCP configurations within backend contexts
3. **Orchestrator-Level Validation** - Validates complete orchestrator configurations with multiple agents

The validator integrates with the security module to ensure all server configurations meet safety requirements, preventing potential security vulnerabilities while maintaining flexibility for legitimate use cases.

## Core Validation Methods

### validate_server_config()

Validates a single MCP server configuration using integrated security validation.

```python
@classmethod
def validate_server_config(cls, config: Dict[str, Any]) -> Dict[str, Any]:
```

**Parameters:**

- `config` (Dict[str, Any]): Server configuration dictionary

**Returns:**

- Dict[str, Any]: Validated and normalized configuration

**Raises:**

- `MCPConfigurationError`: If configuration is invalid or fails security validation

**Example Usage:**

```python
from massgen.mcp_tools.config_validator import MCPConfigValidator

server_config = {
    "name": "weather",
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@fak111/weather-mcp"]
}

validated_config = MCPConfigValidator.validate_server_config(server_config)
```

### validate_backend_mcp_config()

Validates MCP configuration for a backend, handling both dictionary and list formats for server definitions.

```python
@classmethod
def validate_backend_mcp_config(cls, backend_config: Dict[str, Any]) -> Dict[str, Any]:
```

**Parameters:**

- `backend_config` (Dict[str, Any]): Backend configuration dictionary

**Returns:**

- Dict[str, Any]: Validated configuration with normalized server list

**Raises:**

- `MCPConfigurationError`: If configuration is invalid

**Features:**

- Converts dictionary-format server definitions to list format
- Validates each server configuration individually
- Checks for duplicate server names
- Validates tool filtering parameters (`allowed_tools`, `exclude_tools`)

### validate_orchestrator_config()

Validates orchestrator configuration for MCP integration, supporting both dictionary and list agent formats.

```python
@classmethod
def validate_orchestrator_config(cls, orchestrator_config: Dict[str, Any]) -> Dict[str, Any]:
```

**Parameters:**

- `orchestrator_config` (Dict[str, Any]): Orchestrator configuration dictionary

**Returns:**

- Dict[str, Any]: Validated configuration

**Raises:**

- `MCPConfigurationError`: If configuration is invalid

## Configuration Examples

**Note on Command Configuration**: The examples below use the recommended `command` + `args` pattern for stdio transport configuration (e.g., `"command": "npx", "args": ["-y", "@fak111/weather-mcp"]`). The security validator also accepts a single `command` field as a string (which gets parsed and split) or as a list (which gets validated and converted), but the separate `command` and `args` fields provide better clarity and security validation.

### Stdio Transport Configuration

Based on the Gemini MCP example, here's a complete stdio server configuration:

```yaml
agents:
  - id: "gemini2.5flash_mcp_weather"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      mcp_servers:
        - name: "weather"
          type: "stdio"
          command: "npx"
          args: ["-y", "@fak111/weather-mcp"]
          # Optional security configuration
          security:
            level: "strict" # strict, moderate, or permissive
            allowed_executables: ["npx", "node"]
            env:
              level: "strict"
              mode: "denylist"
              denied_vars: ["PATH", "HOME"]
          # Optional environment variables
          env:
            NODE_ENV: "production"
          # Optional working directory
          cwd: "/path/to/working/directory"
```

### Dictionary Format Server Configuration

Based on the Claude Code Discord example:

```yaml
agent:
  id: "claude_code_discord_mcp"
  backend:
    type: "claude_code"
    mcp_servers:
      discord:
        type: "stdio"
        command: "npx"
        args: ["-y", "mcp-discord", "--config", "YOUR_DISCORD_TOKEN"]
        security:
          level: "moderate"
      weather:
        type: "stdio"
        command: "python"
        args: ["-m", "weather_mcp_server"]
```

### Streamable-HTTP Transport Configuration

```yaml
agents:
  - id: "http_mcp_example"
    backend:
      type: "gemini"
      mcp_servers:
        - name: "web_api"
          type: "streamable-http"
          url: "https://api.example.com/mcp"
          headers:
            Authorization: "Bearer ${API_TOKEN}"
            Content-Type: "application/json"
          timeout: 30
          http_read_timeout: 60
          security:
            level: "strict"
            resolve_dns: true
            allow_private_ips: false
            allow_localhost: false
            allowed_hostnames: ["api.example.com"]
```

## Tool Filtering

The validator supports tool filtering at the backend level to control which tools are available:

### allowed_tools Configuration

```yaml
backend:
  type: "claude_code"
  mcp_servers:
    - name: "filesystem"
      type: "stdio"
      command: "python"
      args: ["-m", "filesystem_mcp"]
  # Only allow specific tools
  allowed_tools:
    - "mcp__filesystem__read_file"
    - "mcp__filesystem__write_file"
    - "Read" # Built-in Claude Code tool
    - "Write" # Built-in Claude Code tool
```

### exclude_tools Configuration

```yaml
backend:
  type: "gemini"
  mcp_servers:
    - name: "system_tools"
      type: "stdio"
      command: "python"
      args: ["-m", "system_mcp"]
  # Exclude dangerous tools
  exclude_tools:
    - "mcp__system_tools__delete_file"
    - "mcp__system_tools__format_disk"
```

### Tool Filtering Precedence

When both `allowed_tools` and `exclude_tools` are specified, `exclude_tools` takes precedence and overrides `allowed_tools`. This means that if a tool is listed in both configurations, it will be excluded.

**Precedence Order:**

1. `exclude_tools` - Tools listed here are always blocked
2. `allowed_tools` - Tools listed here are allowed (unless also in exclude_tools)
3. Default behavior - All available tools are allowed if no filtering is specified

**Example demonstrating precedence:**

```yaml
backend:
  type: "claude_code"
  mcp_servers:
    - name: "filesystem"
      type: "stdio"
      command: "python"
      args: ["-m", "filesystem_mcp"]
  # Allow specific filesystem tools
  allowed_tools:
    - "mcp__filesystem__read_file"
    - "mcp__filesystem__write_file"
    - "mcp__filesystem__delete_file" # This will be blocked by exclude_tools
    - "Read" # Built-in Claude Code tool
  # Exclude dangerous operations
  exclude_tools:
    - "mcp__filesystem__delete_file" # This overrides the allowed_tools entry
    - "mcp__filesystem__format_drive"
```

In this example, even though `mcp__filesystem__delete_file` is listed in `allowed_tools`, it will be blocked because it's also listed in `exclude_tools`. The final available tools will be:

- `mcp__filesystem__read_file` ✅ (allowed and not excluded)
- `mcp__filesystem__write_file` ✅ (allowed and not excluded)
- `mcp__filesystem__delete_file` ❌ (excluded, overrides allowed)
- `Read` ✅ (allowed and not excluded)

## Security Integration

The validator integrates with the security module to enforce comprehensive security checks:

### Security Levels

- **strict**: Maximum security, limited executable allowlist, strict environment variable filtering
- **moderate**: Balanced security, expanded executable allowlist, moderate filtering
- **permissive**: Relaxed security for trusted environments, broader allowlist

### Security Configuration Example

```yaml
mcp_servers:
  - name: "secure_server"
    type: "stdio"
    command: "python"
    args: ["-m", "my_mcp_server"]
    security:
      level: "strict"
      allowed_executables: ["python", "python3"]
      env:
        level: "strict"
        mode: "allowlist"
        allowed_vars: ["PYTHONPATH", "MY_APP_CONFIG"]
      resolve_dns: true
      allow_private_ips: false
      allow_localhost: false
```

## Server Naming Conventions

### Enforced Server Name Rules

Server names are validated and enforced by `validate_server_security()` in `security.py` with the following rules:

- **Character validation**: Only alphanumeric characters, underscores, and hyphens (regex: `^[a-zA-Z0-9_-]+$`)
- **Length limit**: Maximum 100 characters
- **Non-empty requirement**: Must be a non-empty string after trimming whitespace

These rules are enforced during configuration validation and will raise `ValueError` if violated.

```yaml
# Valid names
mcp_servers:
  - name: "weather-api"      # Valid: hyphen allowed
  - name: "file_system"      # Valid: underscore allowed
  - name: "server123"        # Valid: alphanumeric
  - name: "my_server_v2"     # Valid: combination

# Invalid names (will raise ValueError)
mcp_servers:
  - name: "server with spaces"  # Invalid: spaces not allowed
  - name: "server@domain"       # Invalid: @ not allowed
  - name: ""                    # Invalid: empty name
```

### Duplicate Detection

The validator automatically detects and prevents duplicate server names in `validate_backend_mcp_config()`:

```python
# This will raise MCPConfigurationError
backend_config = {
    "mcp_servers": [
        {"name": "weather", "type": "stdio", "command": "python", "args": ["-m", "weather_server"]},
        {"name": "weather", "type": "stdio", "command": "python", "args": ["-m", "other_weather"]}  # Duplicate!
    ]
}
```

## Error Handling and Troubleshooting

### Common Validation Errors

#### Missing Required Fields

```python
# Error: Missing 'name' field
server_config = {
    "type": "stdio",
    "command": "python",
    "args": ["-m", "my_server"]
}
# Raises: MCPConfigurationError: Server configuration must include 'name'
```

#### Invalid Transport Types

```python
# Error: Unsupported transport type
server_config = {
    "name": "test",
    "type": "invalid_transport"
}
# Raises: MCPConfigurationError: Unsupported transport type: invalid_transport
```

#### Security Validation Failures

```python
# Error: Dangerous command
server_config = {
    "name": "dangerous",
    "type": "stdio",
    "command": "rm -rf /"  # Contains dangerous characters
}
# Raises: MCPConfigurationError: MCP command cannot contain shell metacharacters: ;
```

#### Duplicate Server Names

```python
# Error: Duplicate names
backend_config = {
    "mcp_servers": [
        {"name": "server1", "type": "stdio", "command": "python", "args": ["-m", "server1"]},
        {"name": "server1", "type": "stdio", "command": "python", "args": ["-m", "server2"]}
    ]
}
# Raises: MCPConfigurationError: Duplicate server names found: ['server1']
```

### Error Context Information

All validation errors include detailed context for debugging:

```python
try:
    MCPConfigValidator.validate_server_config(invalid_config)
except MCPConfigurationError as e:
    print(f"Error: {e}")
    print(f"Context: {e.context}")
    # Context includes: config details, validation source, error location
```

### Debugging Tips

1. **Check Error Context**: Always examine the `context` attribute of `MCPConfigurationError` for detailed information
2. **Validate Incrementally**: Test individual server configurations before combining them
3. **Use Security Levels**: Start with "permissive" security level for testing, then tighten to "strict"
4. **Check Tool Names**: Ensure tool filtering lists use correct tool names (including MCP prefixes)

## Best Practices

### Configuration Structure

1. **Use List Format**: Prefer list format for `mcp_servers` for better readability and validation
2. **Explicit Security**: Always specify security configuration explicitly rather than relying on defaults
3. **Descriptive Names**: Use clear, descriptive server names that indicate their purpose
4. **Environment Isolation**: Use working directories (`cwd`) to isolate server execution environments

### Security Settings

1. **Start Strict**: Begin with "strict" security level and relax only when necessary
2. **Minimal Permissions**: Use `allowed_tools` to grant only necessary tool access
3. **Environment Control**: Carefully manage environment variables, especially in production
4. **URL Validation**: For HTTP transports, use `allowed_hostnames` to restrict connections

### Error Handling Patterns

```python
import logging
import yaml
from massgen.mcp_tools.config_validator import validate_mcp_integration
from massgen.mcp_tools.exceptions import MCPConfigurationError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_and_validate_config(config_path: str) -> Dict[str, Any]:
    """Load and validate MCP configuration with proper error handling."""
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Validate the configuration
        validated_config = validate_mcp_integration(config)

        return validated_config

    except MCPConfigurationError as e:
        logger.error(f"Configuration validation failed: {e}")
        logger.error(f"Error context: {e.context}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading config: {e}")
        raise MCPConfigurationError(
            f"Failed to load configuration from {config_path}",
            context={"config_file": config_path, "original_error": str(e)}
        )
```

### Integration Patterns

```python
# Validate before using in MCP client
def create_mcp_client(backend_config: Dict[str, Any]) -> MCPClient:
    """Create MCP client with validated configuration."""
    # Validate configuration first
    validated_config = MCPConfigValidator.validate_backend_mcp_config(backend_config)

    # Extract validated server configurations
    mcp_servers = validated_config.get("mcp_servers", [])

    # Create client with validated config
    return MCPClient(servers=mcp_servers)
```

## API Reference Summary

| Method                           | Purpose                       | Input                    | Output           | Exceptions              |
| -------------------------------- | ----------------------------- | ------------------------ | ---------------- | ----------------------- |
| `validate_server_config()`       | Validate single server        | Server config dict       | Validated config | `MCPConfigurationError` |
| `validate_backend_mcp_config()`  | Validate backend MCP config   | Backend config dict      | Validated config | `MCPConfigurationError` |
| `validate_orchestrator_config()` | Validate orchestrator config  | Orchestrator config dict | Validated config | `MCPConfigurationError` |
| `validate_mcp_integration()`     | Validate complete integration | Full config dict         | Validated config | `MCPConfigurationError` |

The configuration validator ensures that your MCP setup is secure, consistent, and properly structured, providing clear error messages and context when issues are detected. Use it as the first step in any MCP configuration workflow to catch problems early and maintain system security.
