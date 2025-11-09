# -*- coding: utf-8 -*-
"""
Base class for API parameters handlers.
Provides common functionality for building API parameters across different backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set


class APIParamsHandlerBase(ABC):
    """Abstract base class for API parameter handlers."""

    def __init__(self, backend_instance: Any):
        """Initialize the API params handler.

        Args:
            backend_instance: The backend instance containing necessary formatters and config
        """
        self.backend = backend_instance
        self.formatter = backend_instance.formatter
        self.custom_tool_manager = backend_instance.custom_tool_manager

    @abstractmethod
    async def build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build API parameters for the specific backend.

        Args:
            messages: List of messages in framework format
            tools: List of tools in framework format
            all_params: All parameters including config and runtime params

        Returns:
            Dictionary of API parameters ready for the backend
        """

    @abstractmethod
    def get_excluded_params(self) -> Set[str]:
        """Get backend-specific parameters to exclude from API calls."""

    @abstractmethod
    def get_provider_tools(self, all_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get provider-specific tools based on parameters."""

    def get_base_excluded_params(self) -> Set[str]:
        """Get common parameters to exclude across all backends."""
        return {
            "upload_files",
            # Filesystem manager parameters (handled by base class)
            "cwd",
            "agent_temporary_workspace",
            "agent_temporary_workspace_parent",
            "context_paths",
            "context_write_access_enabled",
            "enforce_read_before_delete",
            "enable_image_generation",
            "enable_mcp_command_line",
            "command_line_allowed_commands",
            "command_line_blocked_commands",
            "command_line_execution_mode",
            "command_line_docker_image",
            "command_line_docker_memory_limit",
            "command_line_docker_cpu_limit",
            "command_line_docker_network_mode",
            "command_line_docker_enable_sudo",
            # Docker credential management parameters
            "command_line_docker_env_file_path",
            "command_line_docker_pass_env_vars",
            "command_line_docker_pass_all_env",
            "command_line_docker_mount_ssh_keys",
            "command_line_docker_mount_git_config",
            "command_line_docker_mount_gh_config",
            "command_line_docker_mount_npm_config",
            "command_line_docker_mount_pypi_config",
            "command_line_docker_additional_mounts",
            # Docker dependency management parameters
            "command_line_docker_auto_install_deps",
            "command_line_docker_auto_install_on_clone",
            "command_line_docker_preinstall_python",
            "command_line_docker_preinstall_npm",
            "command_line_docker_preinstall_system",
            # Backend identification (handled by orchestrator)
            "enable_audio_generation",  # Audio generation parameter
            "type",
            "agent_id",
            "session_id",
            # MCP configuration (handled by base class for MCP backends)
            "mcp_servers",
        }

    def build_base_api_params(
        self,
        messages: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build base API parameters common to most backends."""
        api_params = {"stream": True}

        # Add filtered parameters
        excluded = self.get_excluded_params()
        for key, value in all_params.items():
            if key not in excluded and value is not None:
                api_params[key] = value

        return api_params

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Get MCP tools from backend if available."""
        if hasattr(self.backend, "_mcp_functions") and self.backend._mcp_functions:
            if hasattr(self.backend, "get_mcp_tools_formatted"):
                return self.backend.get_mcp_tools_formatted()
        return []
