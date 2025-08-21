"""
Security utilities for MCP command validation and sanitization. These functions provide comprehensive security checks and validation for MCP servers and tools.
"""

import re
import shlex
import socket
import urllib.parse
from pathlib import Path
import ipaddress
from typing import List, Dict, Any, Optional, Set


def prepare_command(
    command: str,
    max_length: int = 1000,
    *,
    security_level: str = "strict",
    allowed_executables: Optional[Set[str]] = None,
) -> List[str]:
    """
    Sanitize a command and split it into parts before using it to run an MCP server.

    This function provides security by:
    1. Blocking dangerous shell metacharacters
    2. Whitelisting allowed executables (configurable by security level)
    3. Properly parsing shell commands
    4. Validating command length and arguments

    Args:
        command: Command string to sanitize
        max_length: Maximum allowed command length
        security_level: One of {"strict", "moderate", "permissive"}; controls executable allowlist
        allowed_executables: Optional override for allowed executable base-names (case-insensitive)

    Returns:
        List of command parts

    Raises:
        ValueError: If command contains dangerous characters or uses disallowed executables
    """
    if not command or not command.strip():
        raise ValueError("MCP command cannot be empty")

    # Check command length to prevent resource exhaustion
    if len(command) > max_length:
        raise ValueError(f"MCP command too long: {len(command)} > {max_length} characters")

    # Block dangerous characters that could enable shell injection
    dangerous_chars = ["&", "|", ";", "`", "$", "(", ")", "<", ">", "&&", "||", ">>", "<<"]
    for char in dangerous_chars:
        if char in command:
            raise ValueError(f"MCP command cannot contain shell metacharacters: {char}")

    # Block dangerous patterns
    dangerous_patterns = [
        r'\$\{.*\}',  # Variable expansion
        r'\$\(.*\)',  # Command substitution
        r'`.*`',      # Backtick command substitution
        r'\.\./',     # Directory traversal
        r'\\\.\\',    # Windows directory traversal
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, command):
            raise ValueError(f"MCP command contains dangerous pattern: {pattern}")

    # Parse command using shlex for proper shell-like parsing
    try:
        parts = shlex.split(command)
    except ValueError as e:
        raise ValueError(f"Invalid command syntax: {e}")

    if not parts:
        raise ValueError("MCP command cannot be empty after parsing")

    # Validate number of arguments
    if len(parts) > 50:  # Reasonable limit
        raise ValueError(f"Too many command arguments: {len(parts)} > 50")

    # Validate individual argument lengths
    for i, part in enumerate(parts):
        if len(part) > 500:  # Reasonable limit per argument
            raise ValueError(f"Command argument {i} too long: {len(part)} > 500 characters")

    def _default_allowed(level: str) -> Set[str]:
        base_strict: Set[str] = {
            # Python interpreters
            "python", "python3", "python3.8", "python3.9", "python3.10",
            "python3.11", "python3.12", "python3.13", "python3.14", "py",
            # Python package managers
            "uv", "uvx", "pipx", "pip", "pip3",
            # Node.js ecosystem
            "node", "npm", "npx", "yarn", "pnpm", "bun",
            # Other runtimes
            "deno", "java", "ruby", "go", "rust", "cargo",
            # System utilities (limited set)
            "sh", "bash", "zsh", "fish", "powershell", "pwsh", "cmd",
        }
        if level == "strict":
            return base_strict
        if level == "moderate":
            # Extend with common tooling used legitimately
            return base_strict | {"git", "nodejs"}
        if level == "permissive":
            # Still curated; not unbounded
            return base_strict | {"git", "curl", "wget", "nodejs"}
        # Unknown levels fall back to strict
        return base_strict

    allowed = {name.lower() for name in (allowed_executables or _default_allowed(security_level))}

    # Extract executable path and name robustly
    executable_path = Path(parts[0])
    # Basic traversal check (works for both relative and absolute)
    if any(part == ".." for part in executable_path.parts):
        raise ValueError("MCP command path cannot contain parent directory components ('..')")

    # Derive base executable name (strip common extensions)
    base_name = executable_path.name
    lower_name = base_name.lower()
    for ext in (".exe", ".bat", ".cmd", ".ps1"):
        if lower_name.endswith(ext):
            base_name = base_name[: -len(ext)]
            lower_name = lower_name[: -len(ext)]
            break

    if lower_name not in allowed:
        raise ValueError(
            f"MCP command executable '{base_name}' is not allowed (level={security_level}). "
            f"Allowed executables: {sorted(allowed)}"
        )

    return parts


def validate_url(
    url: str,
    *,
    resolve_dns: bool = False,
    allow_private_ips: bool = False,
    allow_localhost: bool = False,
    allowed_hostnames: Optional[Set[str]] = None,
) -> bool:
    """
    Validate URL for security and correctness.

    Args:
        url: URL to validate
        resolve_dns: If True, resolve hostnames and validate the resulting IPs
        allow_private_ips: If True, do not block private/link-local/reserved ranges
        allow_localhost: If True, allow localhost/loopback addresses
        allowed_hostnames: Optional explicit allowlist for hostnames

    Returns:
        True if URL is valid and safe

    Raises:
        ValueError: If URL is invalid or potentially dangerous
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

    if len(url) > 2048:  # Reasonable URL length limit
        raise ValueError(f"URL too long: {len(url)} > 2048 characters")

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}")

    # Validate scheme
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}. Only http and https are allowed.")

    # Validate hostname
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")

    hostname = parsed.hostname.lower()

    # Explicit allowlist for hostnames overrides most checks (still validate scheme/port)
    if allowed_hostnames and hostname in {h.lower() for h in allowed_hostnames}:
        pass
    else:
        # Fast-path string checks for common loopback names
        if not allow_localhost and hostname in {"localhost", "ip6-localhost"}:
            raise ValueError(f"Hostname not allowed for security reasons: {hostname}")

        # Try to interpret hostname as an IP address (IPv4/IPv6)
        ip_obj: Optional[ipaddress._BaseAddress]
        try:
            ip_obj = ipaddress.ip_address(hostname)
        except ValueError:
            ip_obj = None

        def _is_forbidden_ip(ip: ipaddress._BaseAddress) -> bool:
            if allow_private_ips:
                return False
            return (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            )

        if ip_obj is not None:
            # Hostname is a literal IP
            if _is_forbidden_ip(ip_obj) and not (allow_localhost and ip_obj.is_loopback):
                raise ValueError(f"IP address not allowed for security reasons: {hostname}")
        elif resolve_dns:
            # Resolve and validate all resolved addresses
            try:
                port_for_resolution = parsed.port if parsed.port is not None else (443 if parsed.scheme == 'https' else 80)
                addrinfos = socket.getaddrinfo(hostname, port_for_resolution, proto=socket.IPPROTO_TCP)
                for ai in addrinfos:
                    sockaddr = ai[4]
                    ip_literal = sockaddr[0]
                    try:
                        resolved_ip = ipaddress.ip_address(ip_literal)
                        if _is_forbidden_ip(resolved_ip) and not (allow_localhost and resolved_ip.is_loopback):
                            raise ValueError(
                                f"Resolved IP not allowed for security reasons: {hostname} -> {resolved_ip}"
                            )
                    except ValueError:
                        # Skip unparseable entries
                        continue
            except socket.gaierror as e:
                raise ValueError(f"Failed to resolve hostname '{hostname}': {e}")

    # Validate port if specified
    if parsed.port is not None:
        if not (1 <= parsed.port <= 65535):
            raise ValueError(f"Invalid port number: {parsed.port}")

        # Block dangerous ports
        dangerous_ports = {22, 23, 25, 53, 135, 139, 445, 1433, 1521, 3306, 3389, 5432, 6379}
        if parsed.port in dangerous_ports:
            raise ValueError(f"Port {parsed.port} is not allowed for security reasons")

    return True


def validate_environment_variables(
    env: Dict[str, str],
    *,
    level: str = "strict",
    mode: str = "denylist",
    allowed_vars: Optional[Set[str]] = None,
    denied_vars: Optional[Set[str]] = None,
    max_key_length: int = 100,
    max_value_length: int = 1000,
) -> Dict[str, str]:
    """
    Validate environment variables for security.

    Args:
        env: Environment variables dictionary
        level: Security level {"strict", "moderate", "permissive"}
        mode: Validation mode {"denylist", "allowlist"}
        allowed_vars: Optional explicit allowlist (case-insensitive) when mode is allowlist
        denied_vars: Optional explicit denylist (case-insensitive) when mode is denylist
        max_key_length: Maximum allowed environment variable name length
        max_value_length: Maximum allowed environment variable value length

    Returns:
        Validated environment variables

    Raises:
        ValueError: If environment variables contain dangerous values
    """
    if not isinstance(env, dict):
        raise ValueError("Environment variables must be a dictionary")

    validated_env: Dict[str, str] = {}

    # Defaults tuned per level
    default_deny: Set[str] = {
        'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'PYTHONPATH',
        'PWD', 'OLDPWD'
    }
    # In strict mode, also block these commonly sensitive variables
    if level == "strict":
        default_deny |= {'PATH', 'HOME', 'USER', 'USERNAME', 'SHELL'}
    elif level == "moderate":
        # Allow PATH and HOME by default in moderate/permissive
        default_deny |= set()
    elif level == "permissive":
        default_deny |= set()
    else:
        default_deny |= {'PATH', 'HOME'}  # Unknown level fallback

    denylist_active = {v.upper() for v in (denied_vars or set())} or default_deny
    allowlist_active = {v.upper() for v in (allowed_vars or set())}

    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"Environment variable key and value must be strings: {key}={value}")

        if len(key) > max_key_length:
            raise ValueError(f"Environment variable name too long: {len(key)} > {max_key_length}")

        if len(value) > max_value_length:
            raise ValueError(f"Environment variable value too long: {len(value)} > {max_value_length}")

        upper_key = key.upper()

        # Apply allow/deny policies
        if mode == "allowlist":
            if allowlist_active and upper_key not in allowlist_active:
                raise ValueError(f"Environment variable '{key}' is not permitted by allowlist policy")
        else:  # denylist
            if upper_key in denylist_active:
                raise ValueError(f"Environment variable '{key}' is not allowed for security reasons")

        # Check for dangerous patterns in values
        dangerous_patterns = ['$(', '`', '${', '||', '&&', ';', '|']
        for pattern in dangerous_patterns:
            if pattern in value:
                raise ValueError(f"Environment variable '{key}' contains dangerous pattern: {pattern}")

        validated_env[key] = value

    return validated_env


def validate_server_config(config: dict) -> dict:
    """
    Validate and sanitize MCP server configuration with comprehensive security checks.

    Args:
        config: Server configuration dictionary

    Returns:
        Validated configuration dictionary

    Raises:
        ValueError: If configuration is invalid or insecure
    """
    if not isinstance(config, dict):
        raise ValueError("Server configuration must be a dictionary")

    # Create a copy to avoid modifying the original
    validated_config = config.copy()

    # Required fields
    if "name" not in validated_config:
        raise ValueError("Server configuration must include 'name'")

    # Validate server name
    server_name = validated_config["name"]
    if not isinstance(server_name, str) or not server_name.strip():
        raise ValueError("Server name must be a non-empty string")

    if len(server_name) > 100:
        raise ValueError(f"Server name too long: {len(server_name)} > 100 characters")

    # Sanitize server name
    if not re.match(r'^[a-zA-Z0-9_-]+$', server_name):
        raise ValueError("Server name can only contain alphanumeric characters, underscores, and hyphens")

    transport_type = validated_config.get("type", "stdio")

    # Optional security policy configuration
    security_cfg = validated_config.get("security", {}) if isinstance(validated_config.get("security", {}), dict) else {}
    security_level = security_cfg.get("level", "strict")

    if transport_type == "stdio":
        # Validate stdio configuration
        if "command" not in validated_config and "args" not in validated_config:
            raise ValueError("Stdio server configuration must include 'command' or 'args'")

        # Sanitize command if present
        if "command" in validated_config:
            if isinstance(validated_config["command"], str):
                # Convert string command to list with validation
                validated_config["command"] = prepare_command(
                    validated_config["command"],
                    security_level=security_level,
                    allowed_executables=set(security_cfg.get("allowed_executables", []) or []) or None,
                )
            elif isinstance(validated_config["command"], list):
                # Validate each part
                if not validated_config["command"]:
                    raise ValueError("Command list cannot be empty")
                # Validate the command list by joining and re-parsing
                command_str = " ".join(shlex.quote(arg) for arg in validated_config["command"])
                validated_config["command"] = prepare_command(
                    command_str,
                    security_level=security_level,
                    allowed_executables=set(security_cfg.get("allowed_executables", []) or []) or None,
                )
            else:
                raise ValueError("Command must be a string or list")

        # Validate arguments if present
        if "args" in validated_config:
            args = validated_config["args"]
            if not isinstance(args, list):
                raise ValueError("Arguments must be a list")

            for i, arg in enumerate(args):
                if not isinstance(arg, str):
                    raise ValueError(f"Argument {i} must be a string")
                if len(arg) > 500:
                    raise ValueError(f"Argument {i} too long: {len(arg)} > 500 characters")

        # Validate environment variables if present
        if "env" in validated_config:
            env_policy = security_cfg.get("env", {}) if isinstance(security_cfg.get("env", {}), dict) else {}
            validated_config["env"] = validate_environment_variables(
                validated_config["env"],
                level=env_policy.get("level", security_level),
                mode=env_policy.get("mode", "denylist"),
                allowed_vars=set(env_policy.get("allowed_vars", []) or []),
                denied_vars=set(env_policy.get("denied_vars", []) or []),
            )

        # Validate working directory if present
        if "cwd" in validated_config:
            cwd = validated_config["cwd"]
            if not isinstance(cwd, str):
                raise ValueError("Working directory must be a string")
            if len(cwd) > 500:
                raise ValueError(f"Working directory path too long: {len(cwd)} > 500 characters")
            cwd_path = Path(cwd)
            # Allow absolute or relative paths, but forbid parent traversal
            if any(part == ".." for part in cwd_path.parts):
                raise ValueError("Working directory cannot contain parent directory components ('..')")

    elif transport_type == "streamable-http":
        # Validate streamable HTTP configuration
        if "url" not in validated_config:
            raise ValueError(f"{transport_type} server configuration must include 'url'")

        # Use enhanced URL validation
        validate_url(
            validated_config["url"],
            resolve_dns=bool(security_cfg.get("resolve_dns", False)),
            allow_private_ips=bool(security_cfg.get("allow_private_ips", False)),
            allow_localhost=bool(security_cfg.get("allow_localhost", False)),
        )

        # Validate headers if present
        if "headers" in validated_config:
            headers = validated_config["headers"]
            if not isinstance(headers, dict):
                raise ValueError("Headers must be a dictionary")

            for key, value in headers.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ValueError("Header keys and values must be strings")
                if len(key) > 100:
                    raise ValueError(f"Header name too long: {len(key)} > 100")
                if len(value) > 1000:
                    raise ValueError(f"Header value too long: {len(value)} > 1000")

        # Validate timeout if present
        if "timeout" in validated_config:
            timeout = validated_config["timeout"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                raise ValueError("Timeout must be a positive number")
            if timeout > 300:  # 5 minutes max
                raise ValueError(f"Timeout too large: {timeout} > 300 seconds")

    else:
        # List supported transport types for better error messages
        supported_types = ["stdio", "streamable-http"]
        raise ValueError(
            f"Unsupported transport type: {transport_type}. "
            f"Supported types: {supported_types}. "
            f"Note: 'sse' transport was deprecated in MCP v2025-03-26, use 'streamable-http' instead."
        )

    return validated_config


def sanitize_tool_name(tool_name: str, server_name: str) -> str:
    """
    Create a sanitized tool name with server prefix and comprehensive validation.

    Args:
        tool_name: Original tool name
        server_name: Server name for prefixing

    Returns:
        Sanitized tool name with prefix

    Raises:
        ValueError: If tool name or server name is invalid
    """
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("Tool name must be a non-empty string")

    if not isinstance(server_name, str) or not server_name.strip():
        raise ValueError("Server name must be a non-empty string")

    # Length limits
    if len(tool_name) > 100:
        raise ValueError(f"Tool name too long: {len(tool_name)} > 100 characters")

    if len(server_name) > 50:
        raise ValueError(f"Server name too long: {len(server_name)} > 50 characters")

    # Remove any existing mcp__ prefix to avoid double-prefixing
    original_tool_name = tool_name
    if tool_name.startswith("mcp__"):
        tool_name = tool_name[5:]
        # Re-extract server and tool parts if double-prefixed
        if "__" in tool_name:
            parts = tool_name.split("__", 1)
            if len(parts) == 2:
                tool_name = parts[1]

    # Reserved tool names that shouldn't be used
    reserved_names = {
        'connect', 'disconnect', 'list', 'help', 'version', 'status',
        'health', 'ping', 'echo', 'test', 'debug', 'admin', 'system',
        'config', 'settings', 'auth', 'login', 'logout', 'exit', 'quit'
    }

    if tool_name.lower() in reserved_names:
        raise ValueError(f"Tool name '{tool_name}' is reserved and cannot be used")

    # Validate characters - allow alphanumeric, underscore, hyphen, and dot
    if not re.match(r'^[a-zA-Z0-9_.-]+$', tool_name):
        raise ValueError(f"Tool name '{tool_name}' contains invalid characters. Only alphanumeric, underscore, hyphen, and dot are allowed.")

    if not re.match(r'^[a-zA-Z0-9_-]+$', server_name):
        raise ValueError(f"Server name '{server_name}' contains invalid characters. Only alphanumeric, underscore, and hyphen are allowed.")

    # Sanitize names (additional safety)
    safe_server_name = "".join(c for c in server_name if c.isalnum() or c in "_-")
    safe_tool_name = "".join(c for c in tool_name if c.isalnum() or c in "_.-")

    # Ensure names don't start or end with special characters
    safe_server_name = safe_server_name.strip("_-")
    safe_tool_name = safe_tool_name.strip("_.-")

    if not safe_server_name:
        raise ValueError(f"Server name '{server_name}' becomes empty after sanitization")

    if not safe_tool_name:
        raise ValueError(f"Tool name '{tool_name}' becomes empty after sanitization")

    # Create final tool name
    final_name = f"mcp__{safe_server_name}__{safe_tool_name}"

    # Final length check
    if len(final_name) > 200:
        raise ValueError(f"Final tool name too long: {len(final_name)} > 200 characters")

    return final_name


def validate_tool_arguments(arguments: Dict[str, Any], max_depth: int = 5, max_size: int = 10000) -> Dict[str, Any]:
    """
    Validate tool arguments for security and size limits.

    Args:
        arguments: Tool arguments dictionary
        max_depth: Maximum nesting depth allowed
        max_size: Maximum total size of arguments (rough estimate)

    Returns:
        Validated arguments dictionary

    Raises:
        ValueError: If arguments are invalid or too large
    """
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary")

    current_size = 0

    def _add_size(amount: int) -> None:
        nonlocal current_size
        current_size += amount
        if current_size > max_size:
            raise ValueError(f"Tool arguments too large: ~{current_size} > {max_size} bytes")

    def _size_for_primitive(value: Any) -> int:
        # Rough JSON-like size estimation
        if value is None:
            return 4  # null
        if isinstance(value, bool):
            return 4 if value else 5
        if isinstance(value, (int, float)):
            return len(str(value))
        if isinstance(value, str):
            # Account for quotes
            return len(value) + 2
        # Fallback to string conversion with quotes
        return len(str(value)) + 2

    def _validate_value(value: Any, depth: int = 0) -> Any:
        if depth > max_depth:
            raise ValueError(f"Tool arguments nested too deeply: {depth} > {max_depth}")

        if isinstance(value, dict):
            if len(value) > 100:  # Reasonable limit on dict size
                raise ValueError(f"Dictionary too large: {len(value)} > 100 keys")
            # Account for braces
            _add_size(2)
            validated: Dict[str, Any] = {}
            first = True
            for k, v in value.items():
                if not isinstance(k, str):
                    k = str(k)
                # Comma between items
                if not first:
                    _add_size(1)
                first = False
                # Key size with quotes and colon
                _add_size(_size_for_primitive(k) + 1)
                validated[k] = _validate_value(v, depth + 1)
            return validated

        elif isinstance(value, list):
            if len(value) > 1000:  # Reasonable limit on list size
                raise ValueError(f"List too large: {len(value)} > 1000 items")
            # Account for brackets
            _add_size(2)
            validated_list = []
            for idx, item in enumerate(value):
                if idx > 0:
                    _add_size(1)  # comma
                validated_list.append(_validate_value(item, depth + 1))
            return validated_list

        elif isinstance(value, str):
            if len(value) > 10000:  # Reasonable limit on string size
                raise ValueError(f"String too long: {len(value)} > 10000 characters")
            _add_size(_size_for_primitive(value))
            return value

        elif isinstance(value, (int, float, bool)) or value is None:
            _add_size(_size_for_primitive(value))
            return value

        else:
            # Convert other types to string with size limit
            str_value = str(value)
            if len(str_value) > 1000:
                raise ValueError(f"Value too large when converted to string: {len(str_value)} > 1000")
            _add_size(_size_for_primitive(str_value))
            return str_value

    # Validate while streaming size estimation (early termination on overflow)
    return _validate_value(arguments)
