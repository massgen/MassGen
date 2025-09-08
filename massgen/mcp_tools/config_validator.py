"""
Configuration validation for MCP tools integration.Provides comprehensive validation for MCP server configurations,
backend integration settings, and orchestrator coordination parameters.
"""


from ..logger_config import logger
from typing import Dict, Any
from .exceptions import MCPConfigurationError, MCPValidationError


class MCPConfigValidator:
    
    
    @classmethod
    def validate_server_config(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single MCP server configuration using security validator.
        
        Args:
            config: Server configuration dictionary
            
        Returns:
            Validated and normalized configuration
            
        Raises:
            MCPConfigurationError: If configuration is invalid
        """
        try:
            from .security import validate_server_security
            return validate_server_security(config)
        except ValueError as e:
            # Convert security validator errors to consistent MCP error type
            raise MCPConfigurationError(
                str(e),
                context={"config": config, "validation_source": "security_validator"}
            ) from e
    
    @classmethod
    def validate_backend_mcp_config(cls, backend_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate MCP configuration for a backend.
        
        Args:
            backend_config: Backend configuration dictionary
            
        Returns:
            Validated configuration
            
        Raises:
            MCPConfigurationError: If configuration is invalid
        """
        mcp_servers = backend_config.get("mcp_servers")
        if not mcp_servers:
            return backend_config
        
        if isinstance(mcp_servers, dict):
            server_list = []
            for name, config in mcp_servers.items():
                if isinstance(config, dict):
                    server_config = config.copy()
                    server_config["name"] = name
                    server_list.append(server_config)
                else:
                    raise MCPConfigurationError(
                        f"Server configuration for '{name}' must be a dictionary",
                        context={"server_name": name, "config": config}
                    )
            mcp_servers = server_list
        elif not isinstance(mcp_servers, list):
            raise MCPConfigurationError(
                "mcp_servers must be a list or dictionary",
                context={"type": type(mcp_servers).__name__}
            )
        
        # Validate each server configuration
        validated_servers = []
        for i, server_config in enumerate(mcp_servers):
            try:
                validated_servers.append(cls.validate_server_config(server_config))
            except MCPConfigurationError as e:
                # Add context about which server failed
                e.context = e.context or {}
                e.context["server_index"] = i
                raise
        
        # Check for duplicate server names
        server_names = [server["name"] for server in validated_servers]
        duplicates = [name for name in set(server_names) if server_names.count(name) > 1]
        if duplicates:
            raise MCPConfigurationError(
                f"Duplicate server names found: {duplicates}",
                context={"duplicates": duplicates, "all_names": server_names}
            )
        
        # Validate tool filtering parameters if present
        validated_config = backend_config.copy()
        validated_config["mcp_servers"] = validated_servers
        
        # Validate allowed_tools parameter
        allowed_tools = backend_config.get("allowed_tools")
        if allowed_tools is not None:
            if not isinstance(allowed_tools, list):
                raise MCPConfigurationError(
                    "allowed_tools must be a list of strings",
                    context={"type": type(allowed_tools).__name__, "value": allowed_tools}
                )
            for i, tool_name in enumerate(allowed_tools):
                if not isinstance(tool_name, str):
                    raise MCPConfigurationError(
                        f"allowed_tools[{i}] must be a string, got {type(tool_name).__name__}",
                        context={"index": i, "value": tool_name}
                    )
            validated_config["allowed_tools"] = allowed_tools
        
        # Validate exclude_tools parameter
        exclude_tools = backend_config.get("exclude_tools")
        if exclude_tools is not None:
            if not isinstance(exclude_tools, list):
                raise MCPConfigurationError(
                    "exclude_tools must be a list of strings",
                    context={"type": type(exclude_tools).__name__, "value": exclude_tools}
                )
            for i, tool_name in enumerate(exclude_tools):
                if not isinstance(tool_name, str):
                    raise MCPConfigurationError(
                        f"exclude_tools[{i}] must be a string, got {type(tool_name).__name__}",
                        context={"index": i, "value": tool_name}
                    )
            validated_config["exclude_tools"] = exclude_tools
        
        return validated_config
    
    @classmethod
    def validate_orchestrator_config(cls, orchestrator_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate orchestrator configuration for MCP integration.
        
        Args:
            orchestrator_config: Orchestrator configuration dictionary
            
        Returns:
            Validated configuration
        """
        agents = orchestrator_config.get("agents", [])
        validated_config = orchestrator_config.copy()
        
        if isinstance(agents, dict):
            # Handle dict format with backend-level mcp_servers
            validated_agents = {}
            for agent_id, agent_config in agents.items():
                if not isinstance(agent_config, dict):
                    raise MCPConfigurationError(f"Agent '{agent_id}' configuration must be a dictionary")
                
                if isinstance(agent_config.get("backend"), dict) and "mcp_servers" in agent_config["backend"]:
                    agent_cfg_copy = agent_config.copy()
                    agent_cfg_copy["backend"] = cls.validate_backend_mcp_config(agent_config["backend"])
                    validated_agents[agent_id] = agent_cfg_copy
                else:
                    validated_agents[agent_id] = agent_config
            validated_config["agents"] = validated_agents
            
        elif isinstance(agents, list):
            # Handle list format with backend.mcp_servers nesting
            validated_list = []
            for idx, agent_config in enumerate(agents):
                if not isinstance(agent_config, dict):
                    raise MCPConfigurationError(f"Agent at index {idx} must be a dictionary")
                
                if isinstance(agent_config.get("backend"), dict) and "mcp_servers" in agent_config["backend"]:
                    agent_cfg_copy = agent_config.copy()
                    agent_cfg_copy["backend"] = cls.validate_backend_mcp_config(agent_config["backend"])
                    validated_list.append(agent_cfg_copy)
                else:
                    validated_list.append(agent_config)
            validated_config["agents"] = validated_list
            
        else:
            raise MCPConfigurationError("Agents configuration must be a dictionary or list")
        
        return validated_config


def validate_mcp_integration(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate complete MCP integration configuration.
    
    Args:
        config: Complete configuration dictionary
        
    Returns:
        Validated configuration
        
    Raises:
        MCPConfigurationError: If configuration is invalid
    """
    try:
        validator = MCPConfigValidator()
        
        # Validate based on configuration type
        if "agents" in config:
            # Orchestrator configuration
            return validator.validate_orchestrator_config(config)
        elif "mcp_servers" in config:
            # Backend configuration
            return validator.validate_backend_mcp_config(config)
        else:
            # No MCP configuration found
            return config
            
    except Exception as e:
        if isinstance(e, (MCPConfigurationError, MCPValidationError)):
            raise
        else:
            raise MCPConfigurationError(
                f"Unexpected error during configuration validation: {e}",
                context={"original_error": str(e)}
            )