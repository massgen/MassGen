"""
Backend utilities for MCP integration.
Contains all utilities that backends need for MCP functionality.
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple, Callable, Awaitable, AsyncGenerator, Literal
from ..logger_config import logger, log_backend_activity
import random

def _log_mcp_activity(backend_name: Optional[str], message: str, details: Dict[str, Any], agent_id: Optional[str] = None) -> None:
    """Log MCP activity with backend context if available."""
    if backend_name:
        log_backend_activity(backend_name, f"MCP: {message}", details, agent_id=agent_id)
    else:
        logger.info(f"MCP {message}", extra=details)

# Import MCP exceptions
try:
    from .exceptions import (
        MCPError, MCPConnectionError, MCPTimeoutError, MCPServerError,
        MCPValidationError, MCPAuthenticationError, MCPResourceError
    )
    from .config_validator import MCPConfigValidator
    from .circuit_breaker import CircuitBreakerConfig
except ImportError:
    MCPError = Exception
    MCPConnectionError = ConnectionError
    MCPTimeoutError = TimeoutError
    MCPServerError = Exception
    MCPValidationError = ValueError
    MCPAuthenticationError = Exception
    MCPResourceError = Exception
    MCPConfigValidator = None
    CircuitBreakerConfig = None


class Function:
    """Enhanced function wrapper for MCP tools across all backend APIs."""
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], entrypoint: Callable[[str], Awaitable[Any]]) -> None:
        
        self.name = name
        self.description = description
        self.parameters = parameters
        self.entrypoint = entrypoint

    async def call(self, input_str: str) -> Any:
        """Call the function with input string."""
        return await self.entrypoint(input_str)

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert function to OpenAI Response API format."""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
    
    def to_chat_completions_format(self) -> Dict[str, Any]:
        """Convert to Chat Completions API format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
    
    def to_claude_format(self) -> Dict[str, Any]:
        """Convert to Claude API format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
    

    
    def __repr__(self) -> str:
        """String representation of Function."""
        return f"Function(name='{self.name}', description='{self.description[:50]}...')"


class MCPErrorHandler:
    """Standardized MCP error handling utilities."""
    
    @staticmethod
    def get_error_details(
        error: Exception, 
        context: Optional[str] = None, 
        *, 
        log: bool = False
    ) -> Tuple[str, str, str]:
        """Return standardized MCP error info and optionally log.
        
        Returns:
            Tuple of (log_type, user_message, error_category)
        """
        if isinstance(error, MCPConnectionError):
            details = ("connection error", "MCP connection failed", "connection")
        elif isinstance(error, MCPTimeoutError):
            details = ("timeout error", "MCP session timeout", "timeout")
        elif isinstance(error, MCPServerError):
            details = ("server error", "MCP server error", "server")
        elif isinstance(error, MCPValidationError):
            details = ("validation error", "MCP validation failed", "validation")
        elif isinstance(error, MCPAuthenticationError):
            details = ("authentication error", "MCP authentication failed", "auth")
        elif isinstance(error, MCPResourceError):
            details = ("resource error", "MCP resource unavailable", "resource")
        elif isinstance(error, MCPError):
            details = ("MCP error", "MCP error", "general")
        else:
            details = ("unexpected error", "MCP connection failed", "unknown")
        
        if log:
            log_type, user_message, error_category = details
            logger.warning(f"MCP {log_type}: {error}", extra={"context": context or "none"})
        
        return details
    
    @staticmethod
    def is_transient_error(error: Exception) -> bool:
        """Determine if an error is transient and should be retried."""
        if isinstance(error, (MCPConnectionError, MCPTimeoutError)):
            return True
        elif isinstance(error, MCPServerError):
            error_str = str(error).lower()
            return any(keyword in error_str for keyword in [
                "timeout", "connection", "network", "temporary", "unavailable",
                "503", "502", "504", "500", "retry"
            ])
        elif isinstance(error, (ConnectionError, TimeoutError, OSError)):
            return True
        elif isinstance(error, MCPResourceError):
            return True
        return False
    
    @staticmethod
    def log_error(error: Exception, context: str, level: str = "auto", backend_name: Optional[str] = None, agent_id: Optional[str] = None) -> None:
        """Log MCP error with appropriate level and context."""
        log_type, user_message, error_category = MCPErrorHandler.get_error_details(error)
        if level == "auto":
            if error_category in ["connection", "timeout", "resource"]:
                level = "warning"
            elif error_category in ["server", "validation", "auth"]:
                level = "error"
            else:
                level = "error"

        # Log with appropriate level
        log_message = f"MCP {log_type} during {context}: {error}"
        if level == "debug":
            _log_mcp_activity(backend_name, "error (debug)", {"message": log_message}, agent_id=agent_id)
        elif level == "info":
            _log_mcp_activity(backend_name, "error (info)", {"message": log_message}, agent_id=agent_id)
        elif level == "warning":
            _log_mcp_activity(backend_name, "error (warning)", {"message": log_message}, agent_id=agent_id)
        else:
            _log_mcp_activity(backend_name, "error (error)", {"message": log_message}, agent_id=agent_id)
    
    @staticmethod
    def get_retry_delay(attempt: int, base_delay: float = 0.5) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        # Exponential backoff
        backoff_delay = base_delay * (2 ** attempt)

        # Add jitter (10-30% of backoff delay)
        jitter = random.uniform(0.1, 0.3) * backoff_delay

        return backoff_delay + jitter

    @staticmethod
    def is_auth_or_resource_error(error: Exception) -> bool:
        """Check if error is authentication or resource related (non-retryable)."""
        return isinstance(error, (MCPAuthenticationError, MCPResourceError))


class MCPRetryHandler:
    """Handles MCP retry logic with user feedback."""
    
    @staticmethod
    async def handle_retry_error(
        error: Exception,
        retry_count: int,
        max_retries: int,
        stream_chunk_class,
        backend_name: Optional[str] = None
    ) -> Tuple[bool, AsyncGenerator]:
        """Handle MCP retry errors with specific messaging and fallback logic."""
        log_type, user_message, _ = MCPErrorHandler.get_error_details(error)

        # Log the retry attempt
        _log_mcp_activity(backend_name, f"{log_type} on retry", {"attempt": retry_count, "error": str(error)})

        # Check if we've exhausted retries
        if retry_count >= max_retries:
            async def error_chunks():
                yield stream_chunk_class(
                    type="content",
                    content=f"\n⚠️  {user_message} after {max_retries} attempts; falling back to workflow tools\n",
                )
            return False, error_chunks()

        # Continue retrying
        async def empty_chunks():
            yield 
            return
        return True, empty_chunks()
    
    @staticmethod
    async def handle_error_and_fallback(
        error: Exception,
        tool_call_count: int,
        stream_chunk_class,
        backend_name: Optional[str] = None
    ) -> AsyncGenerator:
        """Handle MCP errors with specific messaging and fallback to non-MCP tools."""
        log_type, user_message, _ = MCPErrorHandler.get_error_details(error)

        # Log with specific error type
        _log_mcp_activity(backend_name, "tool call failed", {"call_number": tool_call_count, "error_type": log_type, "error": str(error)})

        # Yield user-friendly error message
        yield stream_chunk_class(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )


class MCPMessageManager:
    """Message history management utilities for MCP integration."""
    
    @staticmethod
    def trim_message_history(
        messages: List[Dict[str, Any]], 
        max_items: int = 200
    ) -> List[Dict[str, Any]]:
        """Trim message history to prevent unbounded growth in MCP execution loop."""
        if max_items <= 0 or len(messages) <= max_items:
            return messages

        preserved = []
        remaining = messages
        
        # Preserve system message if it's the first message
        if messages and messages[0].get("role") == "system":
            preserved = [messages[0]]
            remaining = messages[1:]

        # Keep the most recent items within the limit
        allowed = max_items - len(preserved)
        trimmed_tail = remaining[-allowed:] if allowed > 0 else []
        
        result = preserved + trimmed_tail
        
        if len(messages) > len(result):
            logger.debug("MCP trimmed message history", extra={"original_count": len(messages), "trimmed_count": len(result), "limit": max_items})
        
        return result


class MCPConfigHelper:
    """MCP configuration management utilities."""
    
    @staticmethod
    def validate_backend_config(config: Dict[str, Any], backend_name: Optional[str] = None) -> Dict[str, Any]:
        """Validate backend MCP configuration using existing MCPConfigValidator."""
        if MCPConfigValidator is None:
            _log_mcp_activity(backend_name, "MCPConfigValidator unavailable", {"action": "skipping_validation"})
            return config

        try:
            validator = MCPConfigValidator()
            validated_config = validator.validate(config)
            _log_mcp_activity(backend_name, "configuration validation successful", {})
            return validated_config
        except Exception as e:
            _log_mcp_activity(backend_name, "configuration validation failed", {"error": str(e)})
            raise
    
    @staticmethod
    def extract_tool_filtering_params(config: Dict[str, Any]) -> Tuple[Optional[List], Optional[List]]:
        """Extract allowed_tools and exclude_tools from configuration."""
        allowed_tools = config.get("allowed_tools")
        exclude_tools = config.get("exclude_tools")
        
        # Normalize to lists if provided
        if allowed_tools is not None and not isinstance(allowed_tools, list):
            if isinstance(allowed_tools, str):
                allowed_tools = [allowed_tools]
            else:
                logger.warning("MCP invalid allowed_tools type", extra={"type": type(allowed_tools).__name__, "action": "ignoring"})
                allowed_tools = None

        if exclude_tools is not None and not isinstance(exclude_tools, list):
            if isinstance(exclude_tools, str):
                exclude_tools = [exclude_tools]
            else:
                logger.warning("MCP invalid exclude_tools type", extra={"type": type(exclude_tools).__name__, "action": "ignoring"})
                exclude_tools = None
        
        return allowed_tools, exclude_tools
    
    @staticmethod
    def build_circuit_breaker_config(transport_type: str = "mcp_tools", backend_name: Optional[str] = None) -> Optional[Any]:
        """Build circuit breaker configuration for transport type."""
        if CircuitBreakerConfig is None:
            _log_mcp_activity(backend_name, "CircuitBreakerConfig unavailable", {})
            return None

        try:
            if transport_type == "http":
                # HTTP transport typically needs more tolerance for network issues
                config = CircuitBreakerConfig(
                    max_failures=5,
                    reset_time_seconds=60,
                    backoff_multiplier=2,
                    max_backoff_multiplier=16
                )
            else:
                # Standard configuration for MCP tools (stdio/streamable-http)
                config = CircuitBreakerConfig(
                    max_failures=3,
                    reset_time_seconds=30,
                    backoff_multiplier=2,
                    max_backoff_multiplier=8
                )

            _log_mcp_activity(backend_name, "created circuit breaker config", {"transport_type": transport_type})
            return config
        except Exception as e:
            _log_mcp_activity(backend_name, "failed to create circuit breaker config", {"error": str(e)})
            return None


class MCPCircuitBreakerManager:
    """Circuit breaker management utilities for MCP integration."""

    @staticmethod
    def apply_circuit_breaker_filtering(servers: List[Dict[str, Any]], circuit_breaker, backend_name: Optional[str] = None, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Filter MCP servers based on circuit breaker state."""
        if not circuit_breaker:
            return servers

        filtered_servers = []
        for server in servers:
            server_name = server.get("name", "unnamed")
            if not circuit_breaker.should_skip_server(server_name):
                filtered_servers.append(server)
            else:
                _log_mcp_activity(backend_name, "circuit breaker skipping server", {"server_name": server_name, "reason": "circuit_open"}, agent_id=agent_id)

        return filtered_servers

    @staticmethod
    async def record_success(servers: List[Dict[str, Any]], circuit_breaker, backend_name: Optional[str] = None, agent_id: Optional[str] = None) -> None:
        """Record successful operation for circuit breaker."""
        if not circuit_breaker:
            return

        for server in servers:
            server_name = server.get("name", "unknown")
            try:
                circuit_breaker.record_success(server_name)
                _log_mcp_activity(backend_name, "recorded success for server", {"server_name": server_name}, agent_id=agent_id)
            except Exception as cb_error:
                _log_mcp_activity(backend_name, "circuit breaker record_success failed", {"server_name": server_name, "error": str(cb_error)}, agent_id=agent_id)

    @staticmethod
    async def record_failure(servers: List[Dict[str, Any]], circuit_breaker, error_message: str, backend_name: Optional[str] = None, agent_id: Optional[str] = None) -> None:
        """Record failure for circuit breaker."""
        await MCPCircuitBreakerManager.record_event(servers, circuit_breaker, "failure", error_message, backend_name, agent_id)

    @staticmethod
    async def record_event(
        servers: List[Dict[str, Any]],
        circuit_breaker,
        event: Literal["success", "failure"],
        error_message: Optional[str] = None,
        backend_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """Record success/failure for servers in circuit breaker."""
        if not circuit_breaker:
            return

        count = 0
        for server in servers:
            server_name = server.get("name", "unnamed")
            try:
                if event == "success":
                    circuit_breaker.record_success(server_name)
                else:
                    circuit_breaker.record_failure(server_name)
                count += 1
            except Exception as cb_error:
                _log_mcp_activity(backend_name, "circuit breaker record failed", {"event": event, "server_name": server_name, "error": str(cb_error)}, agent_id=agent_id)

        if count > 0:
            if event == "success":
                _log_mcp_activity(backend_name, "circuit breaker recorded success", {"server_count": count}, agent_id=agent_id)
            else:
                _log_mcp_activity(backend_name, "circuit breaker recorded failure", {"server_count": count, "error": error_message}, agent_id=agent_id)


class MCPResourceManager:
    """Resource management utilities for MCP integration."""

    @staticmethod
    async def cleanup_mcp_client(mcp_client, logger_instance=None, backend_name: Optional[str] = None) -> None:
        """Clean up MCP client connections and reset state."""
        log = logger_instance or logger

        if mcp_client:
            try:
                await mcp_client.disconnect()
                _log_mcp_activity(backend_name, "client disconnected successfully", {})
            except Exception as e:
                _log_mcp_activity(backend_name, "error disconnecting client", {"error": str(e)})

    @staticmethod
    async def setup_mcp_context_manager(backend_instance, backend_name: Optional[str] = None):
        """Setup MCP tools if configured during context manager entry."""
        if hasattr(backend_instance, '_mcp_tools_servers') and backend_instance._mcp_tools_servers and not backend_instance._mcp_initialized:
            try:
                await backend_instance._setup_mcp_tools()
            except Exception as e:
                _log_mcp_activity(backend_name, "setup failed during context entry", {"error": str(e)})
        elif hasattr(backend_instance, 'mcp_servers') and backend_instance.mcp_servers and not backend_instance._mcp_initialized:
            try:
                await backend_instance._setup_mcp_tools()
            except Exception as e:
                _log_mcp_activity(backend_name, "setup failed during context entry", {"error": str(e)})

        return backend_instance

    @staticmethod
    async def cleanup_mcp_context_manager(backend_instance, logger_instance=None, backend_name: Optional[str] = None) -> None:
        """Clean up MCP resources during context manager exit."""
        log = logger_instance or logger

        try:
            if hasattr(backend_instance, 'cleanup_mcp'):
                await backend_instance.cleanup_mcp()
            elif hasattr(backend_instance, '_mcp_client'):
                await MCPResourceManager.cleanup_mcp_client(backend_instance._mcp_client, log, backend_name)
                backend_instance._mcp_client = None
                backend_instance._mcp_initialized = False
                if hasattr(backend_instance, 'functions'):
                    backend_instance.functions.clear()
        except Exception as e:
            _log_mcp_activity(backend_name, "error during cleanup", {"error": str(e)})


class MCPSetupManager:
    """MCP setup and initialization utilities."""

    @staticmethod
    def normalize_mcp_servers(servers) -> List[Dict[str, Any]]:
        """Validate and normalize mcp_servers into a list of dicts."""
        if not servers:
            return []
        if isinstance(servers, dict):
            servers = [servers]
        if not isinstance(servers, list):
            raise ValueError(
                f"mcp_servers must be a list or dict, got {type(servers).__name__}"
            )
        normalized: List[Dict[str, Any]] = []
        for idx, entry in enumerate(servers):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"MCP server configuration at index {idx} must be a dictionary, got {type(entry).__name__}"
                )

            # Validate required fields
            if "type" not in entry:
                raise ValueError(
                    f"MCP server configuration at index {idx} missing required 'type' field. "
                    f"Supported types: 'stdio', 'streamable-http', 'http'"
                )

          
            if "name" not in entry:
                entry = entry.copy()
                entry["name"] = f"server_{idx}"

            normalized.append(entry)
        return normalized

    @staticmethod
    def separate_servers_by_transport_type(servers: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        mcp_tools_servers = []
        http_servers = []

        for server in servers:
            transport_type = server.get("type")
            server_name = server.get("name", "unnamed")

            if not transport_type:
                logger.warning("MCP server missing type field", extra={"server_name": server_name, "supported_types": ["stdio", "streamable-http", "http"], "action": "skipping"})
                continue

            if transport_type in ["stdio", "streamable-http"]:
                # Both stdio and streamable-http use MultiMCPClient
                mcp_tools_servers.append(server)
            elif transport_type == "http":
                http_servers.append(server)
            else:
                logger.warning("MCP unknown transport type", extra={"transport_type": transport_type, "server_name": server_name, "supported_types": ["stdio", "streamable-http", "http"], "action": "skipping"})

        return mcp_tools_servers, http_servers


class MCPExecutionManager:
    """MCP function execution utilities with retry logic."""

    @staticmethod
    async def execute_function_with_retry(
        function_name: str,
        args: Dict[str, Any],
        functions: Dict[str, Function],
        max_retries: int = 3,
        stats_callback: Optional[Callable] = None,
        circuit_breaker_callback: Optional[Callable] = None,
        logger_instance = None
    ) -> Any:
        """Execute MCP function with exponential backoff retry logic.

        Args:
            function_name: Name of the MCP function to call
            args: Function arguments as dictionary
            functions: Dictionary of available Function objects
            max_retries: Maximum number of retry attempts
            stats_callback: Optional callback for tracking stats (call_count, failures)
            circuit_breaker_callback: Optional callback for circuit breaker events
            logger_instance: Logger instance to use (defaults to module logger)

        Returns:
            Function result or structured error payload if all retries fail
        """
        import json
        import asyncio
        import random

        log = logger_instance or logger

        # Track call attempt
        if stats_callback:
            call_index = await stats_callback("increment_calls")
        else:
            call_index = 1

        for attempt in range(max_retries + 1):
            try:
                # Convert args to JSON string for the function call
                arguments_json = json.dumps(args)

                # Execute the MCP function
                result = await functions[function_name].call(arguments_json)

                # Successful execution
                if attempt > 0:
                    logger.info("MCP function succeeded on retry", extra={"function_name": function_name, "call_index": call_index, "retry_attempt": attempt})

                return result

            except Exception as e:
                # Check if this is a non-retryable error
                if MCPErrorHandler.is_auth_or_resource_error(e):
                    MCPErrorHandler.log_error(e, f"function call {function_name}")
                    if circuit_breaker_callback:
                        await circuit_breaker_callback("failure", str(e))
                    if stats_callback:
                        await stats_callback("increment_failures")
                    return {"error": str(e), "type": "auth_resource_error", "function": function_name}

                is_last_attempt = attempt == max_retries

                if MCPErrorHandler.is_transient_error(e) and not is_last_attempt:
                    # Calculate exponential backoff with jitter
                    delay = MCPErrorHandler.get_retry_delay(attempt)

                    MCPErrorHandler.log_error(e, f"function call {function_name} (attempt {attempt + 1})")
                    logger.info("MCP retrying function call", extra={"delay_seconds": delay})

                    await asyncio.sleep(delay)
                    continue
                else:
                    # Final failure
                    MCPErrorHandler.log_error(e, f"function call {function_name} (final)")
                    if circuit_breaker_callback:
                        await circuit_breaker_callback("failure", str(e))
                    if stats_callback:
                        await stats_callback("increment_failures")

                    return {"error": str(e), "type": "execution_error", "function": function_name}
        return {"error": "Max retries exceeded", "type": "retry_exhausted", "function": function_name}
