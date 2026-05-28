"""
MCP Server Registry

Centralized registry of recommended MCP servers for MassGen.
When auto_discover_custom_tools is enabled, these servers are automatically
included in the agent's MCP configuration (if API keys are available).

Available servers:
- Context7: Up-to-date documentation for libraries and frameworks
- Brave Search: Web search via Brave API (requires API key)
- Exa Search: AI-powered web search via Exa API (requires API key)
- Parallel Search: LLM-optimized web search via Parallel API (anonymous-friendly;
  optional API key for higher rate limits)
"""

import os
from copy import deepcopy
from typing import Any

# Registry of recommended MCP servers
MCP_SERVER_REGISTRY: dict[str, dict[str, Any]] = {
    "context7": {
        "name": "context7",
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
        "description": "Up-to-date code documentation for libraries/frameworks. Outputs large content - recommend writing to files.",
        "requires_api_key": False,
        "optional_api_key_env_var": "CONTEXT7_API_KEY",
        "notes": "Optional API key at https://context7.com/dashboard for higher rate limits. Write large outputs to files for easier parsing.",
        "security": {
            "level": "moderate",
        },
    },
    "brave_search": {
        "name": "brave_search",
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@brave/brave-search-mcp-server"],
        "env": {
            "BRAVE_API_KEY": "${BRAVE_API_KEY}",
        },
        "description": "Web search via Brave API. Free tier provides 2000 queries/month.",
        "requires_api_key": True,
        "api_key_env_var": "BRAVE_API_KEY",
        "rate_limit_warning": "Free tier limited to 2000 queries/month. Avoid parallel queries to prevent rate limiting.",
        "notes": "Get API key at https://brave.com/search/api/. Consider sequential execution for multiple queries.",
        "security": {
            "level": "moderate",
        },
    },
    "exa_search": {
        "name": "exa_search",
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "exa-mcp-server"],
        "env": {
            "EXA_API_KEY": "${EXA_API_KEY}",
        },
        "description": ("Exa's official MCP server via npm package. " "Provides AI-powered web search and page fetch tools, " "with additional advanced search options in current Exa docs."),
        "requires_api_key": True,
        "api_key_env_var": "EXA_API_KEY",
        "notes": (
            "Get API key at https://exa.ai/. MassGen uses Exa's official "
            "npm package (npx -y exa-mcp-server); Exa's docs also recommend "
            "the hosted MCP endpoint https://mcp.exa.ai/mcp for "
            "HTTP-capable clients."
        ),
        "security": {
            "level": "moderate",
        },
    },
    "parallel_search": {
        "name": "parallel_search",
        "type": "streamable-http",
        "url": "https://search.parallel.ai/mcp",
        "description": (
            "Parallel's hosted Search MCP server. Provides LLM-optimized "
            "web search and URL extraction tools that return ranked, "
            "compressed markdown excerpts suitable for direct model "
            "consumption. Works without an API key for free anonymous "
            "use; set PARALLEL_API_KEY for higher rate limits."
        ),
        "requires_api_key": False,
        "optional_api_key_env_var": "PARALLEL_API_KEY",
        "notes": (
            "Free anonymous access for light/exploratory use. For higher "
            "rate limits in production, get a key at https://platform.parallel.ai "
            "and add 'headers: {Authorization: \"Bearer ${PARALLEL_API_KEY}\"}' "
            "to your mcp_servers entry. Docs: "
            "https://docs.parallel.ai/integrations/mcp/search-mcp"
        ),
        "security": {
            "level": "moderate",
        },
    },
}


def is_api_key_available(env_var_name: str) -> bool:
    """Check if an API key environment variable is set and non-empty.

    Args:
        env_var_name: Name of environment variable to check

    Returns:
        True if env var exists and is non-empty, False otherwise
    """
    value = os.environ.get(env_var_name)
    return value is not None and value.strip() != ""


def get_server_config(server_name: str, apply_api_key_logic: bool = True) -> dict[str, Any] | None:
    """Get configuration for a specific MCP server from registry.

    Args:
        server_name: Name of the server (e.g., "context7", "serena", "brave_search")
        apply_api_key_logic: If True, adds optional API keys when available (e.g., Context7)

    Returns:
        Deep copy of server configuration dict, or None if server not found

    Example:
        >>> config = get_server_config("context7")
        >>> config['name']
        'context7'
    """
    if server_name not in MCP_SERVER_REGISTRY:
        return None

    # Deep copy to avoid modifying the registry
    config = deepcopy(MCP_SERVER_REGISTRY[server_name])

    # Handle optional API key for Context7
    if apply_api_key_logic and server_name == "context7":
        optional_key_var = config.get("optional_api_key_env_var")
        if optional_key_var and is_api_key_available(optional_key_var):
            # Add --api-key argument with the API key value
            api_key_value = os.environ.get(optional_key_var)
            config["args"].extend(["--api-key", api_key_value])

    return config


def get_available_servers(check_api_keys: bool = True) -> list[str]:
    """Get list of registry server names that are available for use.

    Args:
        check_api_keys: If True, only include servers where required API keys are available.
                       If False, return all servers regardless of API key status.

    Returns:
        List of server names that can be used

    Example:
        >>> # If BRAVE_API_KEY is not set:
        >>> get_available_servers(check_api_keys=True)
        ['context7']

        >>> # If BRAVE_API_KEY is set:
        >>> get_available_servers(check_api_keys=True)
        ['context7', 'brave_search']
    """
    available = []

    for server_name, config in MCP_SERVER_REGISTRY.items():
        if not check_api_keys:
            # Include all servers
            available.append(server_name)
        else:
            # Check if required API key is available
            if config.get("requires_api_key", False):
                api_key_var = config.get("api_key_env_var")
                if api_key_var and is_api_key_available(api_key_var):
                    available.append(server_name)
            else:
                # No API key required
                available.append(server_name)

    return available


def get_auto_discovery_servers() -> list[dict[str, Any]]:
    """Get list of MCP server configurations to include when auto-discovery is enabled.

    Only includes servers where:
    - No API key is required, OR
    - Required API key is available in environment

    Returns:
        List of server configuration dicts ready to merge into mcp_servers

    Example:
        >>> servers = get_auto_discovery_servers()
        >>> len(servers) >= 1  # At least context7 (no API key required)
        True
    """
    available_server_names = get_available_servers(check_api_keys=True)

    # Get full configurations for available servers
    configs = []
    for server_name in available_server_names:
        config = get_server_config(server_name, apply_api_key_logic=True)
        if config:
            configs.append(config)

    return configs


def get_missing_api_keys() -> dict[str, str]:
    """Get information about registry servers that require missing API keys.

    Returns:
        Dict mapping server name to missing API key environment variable name

    Example:
        >>> missing = get_missing_api_keys()
        >>> # If BRAVE_API_KEY not set:
        >>> missing.get('brave_search')
        'BRAVE_API_KEY'
    """
    missing = {}

    for server_name, config in MCP_SERVER_REGISTRY.items():
        if config.get("requires_api_key", False):
            api_key_var = config.get("api_key_env_var")
            if api_key_var and not is_api_key_available(api_key_var):
                missing[server_name] = api_key_var

    return missing


def get_registry_info() -> dict[str, Any]:
    """Get summary information about the MCP server registry.

    Returns:
        Dict with registry statistics and status

    Example:
        >>> info = get_registry_info()
        >>> info['total_servers']
        3
        >>> 'context7' in info['available_servers']
        True
    """
    return {
        "total_servers": len(MCP_SERVER_REGISTRY),
        "available_servers": get_available_servers(check_api_keys=True),
        "unavailable_servers": list(get_missing_api_keys().keys()),
        "missing_api_keys": get_missing_api_keys(),
        "server_names": list(MCP_SERVER_REGISTRY.keys()),
    }
