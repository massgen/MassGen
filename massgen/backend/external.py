# -*- coding: utf-8 -*-
"""
External agent backend for integrating external agent frameworks and systems.
Supports AG2, LangChain, and other external agents through adapters.
"""
from typing import Any, AsyncGenerator, Dict, List, Optional

from massgen.adapters import adapter_registry
from massgen.backend.base import FilesystemSupport, LLMBackend, StreamChunk


class ExternalAgentBackend(LLMBackend):
    """
    Backend for integrating external agent frameworks through adapters.

    This backend acts as a bridge between MassGen's orchestration system
    and external agent frameworks like AG2 (AutoGen), LangChain, etc.
    """

    def __init__(
        self,
        adapter_type: str,
        api_key: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize external agent backend.

        Args:
            adapter_type: Framework/adapter type (e.g., "ag2", "langchain")
            api_key: Optional API key for frameworks that need it
            **kwargs: Framework-specific configuration
        """
        self.adapter_type = adapter_type.lower()

        # Get adapter class from registry
        if self.adapter_type not in adapter_registry:
            raise ValueError(
                f"Unsupported framework: {self.adapter_type}. " f"Supported frameworks: {', '.join(adapter_registry.keys())}",
            )

        adapter_class = adapter_registry[self.adapter_type]

        # Extract framework-specific config
        adapter_config = self._extract_adapter_config(kwargs)

        # Initialize adapter before calling super().__init__
        # This is needed because base class may call get_filesystem_support()
        self.adapter = adapter_class(**adapter_config)

        # Now initialize base class
        super().__init__(api_key=api_key, **kwargs)

    def _extract_adapter_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract framework-specific configuration."""
        # Remove base backend parameters
        excluded_params = self.get_base_excluded_config_params()

        # Additional ExternalAgentBackend-specific exclusions
        excluded_params.update(
            {
                "",  # Already handled
            },
        )

        # Return remaining config for framework
        return {k: v for k, v in config.items() if k not in excluded_params}

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream response from external agent with tool support.

        Args:
            messages: Conversation messages
            tools: Available tools
            **kwargs: Additional parameters

        Yields:
            StreamChunk: Response chunks
        """
        # Forward to adapter
        async for chunk in self.adapter.execute_streaming(messages, tools, **kwargs):
            yield chunk

    def get_provider_name(self) -> str:
        """Get provider name."""
        return f"{self.adapter_type}"

    def get_filesystem_support(self) -> FilesystemSupport:
        """
        External agents typically use MCP for filesystem operations.

        Some frameworks may have their own filesystem tools, but we
        standardize on MCP for consistency.
        """
        # Check if adapter has specific filesystem support
        if hasattr(self.adapter, "get_filesystem_support"):
            return self.adapter.get_filesystem_support()

        # Default to MCP support for external agents
        return FilesystemSupport.MCP

    def is_stateful(self) -> bool:
        """Check if this backend maintains conversation state."""
        # Most external frameworks are stateful
        if hasattr(self.adapter, "is_stateful"):
            return self.adapter.is_stateful()
        return False

    def clear_history(self) -> None:
        """Clear conversation history."""
        if hasattr(self.adapter, "clear_history"):
            self.adapter.clear_history()

    def reset_state(self) -> None:
        """Reset backend state."""
        if hasattr(self.adapter, "reset_state"):
            self.adapter.reset_state()
