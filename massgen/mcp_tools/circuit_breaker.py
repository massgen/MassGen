"""
MCP Circuit Breaker implementation for handling server failures.

Provides unified failure tracking and circuit breaker functionality across all MCP integrations.
"""

import time
from ..logger_config import logger, log_backend_activity
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field


def _log_mcp_activity(backend_name: Optional[str], message: str, details: Dict[str, Any], agent_id: Optional[str] = None) -> None:
    """Log MCP activity with backend context if available."""
    if backend_name:
        log_backend_activity(backend_name, f"MCP: {message}", details, agent_id=agent_id)
    else:
        logger.info(f"MCP {message}", extra=details)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    max_failures: int = 3
    reset_time_seconds: int = 300
    backoff_multiplier: int = 2
    max_backoff_multiplier: int = 8


@dataclass
class ServerStatus:
    """Track failure status for a single server."""
    failure_count: int = 0
    last_failure_time: float = 0.0
    
    @property
    def is_failing(self) -> bool:
        """Check if server is currently in failing state."""
        return self.failure_count > 0


class MCPCircuitBreaker:
    """
    Circuit breaker for MCP server failure handling.

    Provides consistent failure tracking and exponential backoff across all MCP integrations.
    Prevents repeated connection attempts to failing servers while allowing recovery.
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None, backend_name: Optional[str] = None):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration. Uses default if None.
            backend_name: Name of the backend using this circuit breaker for logging context.
        """
        self.config = config or CircuitBreakerConfig()
        self.backend_name = backend_name
        self._server_status: Dict[str, ServerStatus] = {}
        
    def should_skip_server(self, server_name: str) -> bool:
        """
        Check if server should be skipped due to circuit breaker.
        
        Args:
            server_name: Name of the server to check
            
        Returns:
            True if server should be skipped, False otherwise
        """
        if server_name not in self._server_status:
            return False
            
        status = self._server_status[server_name]
        
        # Check if below failure threshold
        if status.failure_count < self.config.max_failures:
            return False
            
        current_time = time.monotonic()
        time_since_failure = current_time - status.last_failure_time
        
        # Calculate backoff time with exponential backoff (capped)
        backoff_time = self._calculate_backoff_time(status.failure_count)
        
        if time_since_failure > backoff_time:
            # Reset failure count after backoff period
            _log_mcp_activity(
                self.backend_name,
                "Circuit breaker reset for server",
                {"server_name": server_name, "backoff_time_seconds": backoff_time},
            )
            self._reset_server(server_name)
            return False
            
        return True
        
    def record_failure(self, server_name: str) -> None:
        """
        Record a server failure for circuit breaker.
        
        Args:
            server_name: Name of the server that failed
        """
        current_time = time.monotonic()
        
        if server_name not in self._server_status:
            self._server_status[server_name] = ServerStatus()
            
        status = self._server_status[server_name]
        status.failure_count += 1
        status.last_failure_time = current_time
        
        if status.failure_count >= self.config.max_failures:
            backoff_time = self._calculate_backoff_time(status.failure_count)
            _log_mcp_activity(
                self.backend_name,
                "Server circuit breaker opened",
                {
                    "server_name": server_name,
                    "failure_count": status.failure_count,
                    "backoff_time_seconds": backoff_time,
                },
            )
        else:
            _log_mcp_activity(
                self.backend_name,
                "Server failure recorded",
                {
                    "server_name": server_name,
                    "failure_count": status.failure_count,
                    "max_failures": self.config.max_failures,
                },
            )
            
    def record_success(self, server_name: str) -> None:
        """
        Record a successful connection, resetting failure count.
        
        Args:
            server_name: Name of the server that succeeded
        """
        if server_name in self._server_status:
            old_status = self._server_status[server_name]
            if old_status.failure_count > 0:
                _log_mcp_activity(
                    self.backend_name,
                    "Server recovered",
                    {"server_name": server_name, "previous_failure_count": old_status.failure_count},
                )
            self._reset_server(server_name)
            
    def get_server_status(self, server_name: str) -> Tuple[int, float, bool]:
        """
        Get detailed status for a server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            Tuple of (failure_count, last_failure_time, is_circuit_open)
        """
        if server_name not in self._server_status:
            return (0, 0.0, False)
            
        status = self._server_status[server_name]
        is_circuit_open = (
            status.failure_count >= self.config.max_failures and 
            self.should_skip_server(server_name)
        )
        
        return (status.failure_count, status.last_failure_time, is_circuit_open)
        
    def get_all_failing_servers(self) -> Dict[str, Dict[str, any]]:
        """
        Get status of all servers with failures.
        
        Returns:
            Dictionary mapping server names to status information
        """
        failing_servers = {}
        current_time = time.monotonic()
        
        for server_name, status in self._server_status.items():
            if status.is_failing:
                backoff_time = self._calculate_backoff_time(status.failure_count)
                time_since_failure = current_time - status.last_failure_time
                time_remaining = max(0, backoff_time - time_since_failure)
                
                failing_servers[server_name] = {
                    "failure_count": status.failure_count,
                    "last_failure_time": status.last_failure_time,
                    "backoff_time": backoff_time,
                    "time_remaining": time_remaining,
                    "is_circuit_open": time_remaining > 0 and status.failure_count >= self.config.max_failures
                }
                
        return failing_servers
        
    def reset_all_servers(self) -> None:
        """Reset circuit breaker state for all servers."""
        reset_count = len([s for s in self._server_status.values() if s.is_failing])
        if reset_count > 0:
            _log_mcp_activity(
                self.backend_name,
                "Resetting circuit breaker for all servers",
                {"server_count": reset_count},
            )
        self._server_status.clear()
        
    def _reset_server(self, server_name: str) -> None:
        """Reset circuit breaker state for a specific server."""
        if server_name in self._server_status:
            del self._server_status[server_name]
            
    def _calculate_backoff_time(self, failure_count: int) -> float:
        """
        Calculate backoff time based on failure count.
        
        Args:
            failure_count: Number of failures
            
        Returns:
            Backoff time in seconds
        """
        if failure_count < self.config.max_failures:
            return 0.0
            
        # Exponential backoff: base_time * (multiplier ^ (failures - max_failures))
        exponent = failure_count - self.config.max_failures
        multiplier = min(
            self.config.backoff_multiplier ** exponent,
            self.config.max_backoff_multiplier
        )
        
        return self.config.reset_time_seconds * multiplier
        
    def __repr__(self) -> str:
        """String representation for debugging."""
        failing_count = len([s for s in self._server_status.values() if s.is_failing])
        total_servers = len(self._server_status)
        return f"MCPCircuitBreaker(failing={failing_count}/{total_servers}, config={self.config})"