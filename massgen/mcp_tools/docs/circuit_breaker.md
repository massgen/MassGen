# MCP Circuit Breaker Documentation

## Overview

The `MCPCircuitBreaker` is a resilience pattern implementation designed to handle server failures gracefully and prevent cascading failures in MCP (Model Context Protocol) integrations. It provides automatic failure detection, exponential backoff, and recovery mechanisms to maintain system stability when MCP servers become unreliable or unavailable.

### Key Features

- **Failure Tracking**: Monitors server health and tracks failure counts
- **Exponential Backoff**: Implements configurable backoff strategies to avoid overwhelming failing servers
- **Automatic Recovery**: Allows servers to recover naturally after backoff periods
- **Circuit Opening**: Temporarily bypasses failing servers to prevent cascading failures
- **Monitoring**: Provides detailed status information for all tracked servers

## Architecture

The circuit breaker consists of three main components:

1. **CircuitBreakerConfig**: Configuration class defining behavior parameters
2. **ServerStatus**: Individual server state tracking
3. **MCPCircuitBreaker**: Main circuit breaker implementation

## Configuration

### CircuitBreakerConfig

The `CircuitBreakerConfig` class defines the behavior of the circuit breaker:

```python
from massgen.mcp_tools.circuit_breaker import CircuitBreakerConfig

# Default configuration
config = CircuitBreakerConfig()
print(f"Max failures: {config.max_failures}")           # 3
print(f"Reset time: {config.reset_time_seconds}")       # 300 seconds (5 minutes)
print(f"Backoff multiplier: {config.backoff_multiplier}") # 2
print(f"Max backoff: {config.max_backoff_multiplier}")  # 8

# Custom configuration for high-traffic scenarios
high_traffic_config = CircuitBreakerConfig(
    max_failures=5,              # Allow more failures before circuit opens
    reset_time_seconds=60,       # Shorter base reset time
    backoff_multiplier=1.5,      # Gentler backoff progression
    max_backoff_multiplier=4     # Lower maximum backoff
)

# Custom configuration for critical services
critical_config = CircuitBreakerConfig(
    max_failures=1,              # Fail fast for critical services
    reset_time_seconds=600,      # Longer base reset time (10 minutes)
    backoff_multiplier=3,        # Aggressive backoff
    max_backoff_multiplier=16    # Higher maximum backoff
)
```

#### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_failures` | int | 3 | Number of failures before circuit opens |
| `reset_time_seconds` | int | 300 | Base reset time in seconds (5 minutes) |
| `backoff_multiplier` | int | 2 | Exponential backoff multiplier |
| `max_backoff_multiplier` | int | 8 | Maximum backoff multiplier cap |

### ServerStatus

The `ServerStatus` dataclass tracks the state of individual servers:

```python
from massgen.mcp_tools.circuit_breaker import ServerStatus

# Server status attributes
status = ServerStatus(
    failure_count=2,
    last_failure_time=1234567890.0
)

print(f"Is failing: {status.is_failing}")  # True (failure_count > 0)
```

## API Reference

### MCPCircuitBreaker

#### Constructor

```python
from massgen.mcp_tools.circuit_breaker import MCPCircuitBreaker, CircuitBreakerConfig

# Default configuration
circuit_breaker = MCPCircuitBreaker()

# Custom configuration
config = CircuitBreakerConfig(max_failures=5, reset_time_seconds=120)
circuit_breaker = MCPCircuitBreaker(config)
```

#### should_skip_server(server_name: str) -> bool

Checks if a server should be skipped due to circuit breaker state.

```python
# Check if server should be bypassed
if circuit_breaker.should_skip_server("weather_server"):
    print("Server is currently failing, skipping...")
else:
    print("Server is healthy, proceeding with connection...")
```

**Returns**: `True` if server should be skipped, `False` if safe to use.

#### record_failure(server_name: str) -> None

Records a server failure and updates circuit breaker state.

```python
try:
    # Attempt server operation
    await client.connect()
except MCPConnectionError:
    # Record the failure
    circuit_breaker.record_failure("weather_server")
    print("Failure recorded for weather_server")
```

#### record_success(server_name: str) -> None

Records a successful operation and resets failure count.

```python
try:
    result = await client.call_tool("get_weather", {"city": "Tokyo"})
    # Record success to reset failure count
    circuit_breaker.record_success("weather_server")
    print("Success recorded, server recovered")
except Exception as e:
    circuit_breaker.record_failure("weather_server")
```

#### get_server_status(server_name: str) -> Tuple[int, float, bool]

Returns detailed status information for a specific server.

```python
failure_count, last_failure_time, is_circuit_open = circuit_breaker.get_server_status("weather_server")

print(f"Failure count: {failure_count}")
print(f"Last failure: {last_failure_time}")
print(f"Circuit open: {is_circuit_open}")
```

**Returns**: Tuple of `(failure_count, last_failure_time, is_circuit_open)`

**Note**: This method may reset the server state if the backoff period has expired, as it internally calls `should_skip_server()` to determine circuit status. For read-only inspection without side effects, use `get_all_failing_servers()` instead.

#### get_all_failing_servers() -> Dict[str, Dict[str, Any]]

Returns status information for all servers with failures.

```python
failing_servers = circuit_breaker.get_all_failing_servers()

for server_name, status in failing_servers.items():
    print(f"Server: {server_name}")
    print(f"  Failures: {status['failure_count']}")
    print(f"  Backoff time: {status['backoff_time']:.1f}s")
    print(f"  Time remaining: {status['time_remaining']:.1f}s")
    print(f"  Circuit open: {status['is_circuit_open']}")
```

#### reset_all_servers() -> None

Manually resets circuit breaker state for all servers.

```python
# Reset all servers (useful for maintenance or testing)
circuit_breaker.reset_all_servers()
print("All servers reset")
```

## Integration Examples

### MCPClient Integration

The circuit breaker is automatically integrated into `MCPClient` through the `MultiMCPClient`:

```python
import asyncio
from massgen.mcp_tools.client import MCPClient
from massgen.mcp_tools.circuit_breaker import MCPCircuitBreaker, CircuitBreakerConfig
from massgen.mcp_tools.exceptions import MCPConnectionError

async def example_single_client():
    # Circuit breaker is handled internally by MultiMCPClient
    # but you can create your own for custom logic

    config = CircuitBreakerConfig(max_failures=2, reset_time_seconds=60)
    circuit_breaker = MCPCircuitBreaker(config)

    server_config = {
        "name": "weather_server",
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@fak111/weather-mcp"]
    }

    # Check circuit breaker before attempting connection
    if circuit_breaker.should_skip_server("weather_server"):
        print("Server is failing, skipping connection attempt")
        return

    try:
        async with MCPClient(server_config) as client:
            result = await client.call_tool("get_weather", {"city": "Tokyo"})
            circuit_breaker.record_success("weather_server")
            return result
    except MCPConnectionError as e:
        circuit_breaker.record_failure("weather_server")
        print(f"Connection failed: {e}")
        raise
```

### MultiMCPClient Integration

The `MultiMCPClient` has built-in circuit breaker functionality:

```python
import asyncio
from massgen.mcp_tools.client import MultiMCPClient
from massgen.mcp_tools.exceptions import MCPConnectionError

async def example_multi_client():
    server_configs = [
        {
            "name": "weather_server",
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@fak111/weather-mcp"]
        },
        {
            "name": "file_server",
            "type": "stdio",
            "command": "python",
            "args": ["-m", "file_mcp_server"]
        }
    ]

    async with MultiMCPClient(server_configs) as multi_client:
        # Circuit breaker automatically handles failing servers
        try:
            # This will skip servers that are currently failing
            result = await multi_client.call_tool("mcp__weather_server__get_weather",
                                                 {"city": "Tokyo"})
            print(f"Weather result: {result}")
        except MCPConnectionError as e:
            print(f"All weather servers are failing: {e}")

        # Check circuit breaker status
        health_status = await multi_client.health_check_all()
        print(f"Server health: {health_status}")
```

## Exponential Backoff Algorithm

The circuit breaker implements exponential backoff to gradually increase wait times for failing servers:

### Calculation Formula

```
backoff_time = reset_time_seconds * min(backoff_multiplier^(failures - max_failures), max_backoff_multiplier)
```

### Example Calculations

With default configuration (`reset_time_seconds=300`, `backoff_multiplier=2`, `max_backoff_multiplier=8`):

```python
# Failure progression example
failures = [3, 4, 5, 6, 7, 8, 9, 10]
backoff_times = []

for failure_count in failures:
    if failure_count >= 3:  # max_failures
        exponent = failure_count - 3
        multiplier = min(2 ** exponent, 8)  # Cap at max_backoff_multiplier
        backoff_time = 300 * multiplier
        backoff_times.append(backoff_time)
        print(f"Failure {failure_count}: {backoff_time}s ({backoff_time/60:.1f} minutes)")

# Output:
# Failure 3: 300s (5.0 minutes)
# Failure 4: 600s (10.0 minutes)
# Failure 5: 1200s (20.0 minutes)
# Failure 6: 2400s (40.0 minutes)
# Failure 7: 2400s (40.0 minutes) - capped
# Failure 8: 2400s (40.0 minutes) - capped
```

### Custom Backoff Examples

```python
# Gentle backoff for development
dev_config = CircuitBreakerConfig(
    max_failures=3,
    reset_time_seconds=30,      # 30 seconds base
    backoff_multiplier=1.5,     # Slower progression
    max_backoff_multiplier=4    # Max 2 minutes
)

# Aggressive backoff for production
prod_config = CircuitBreakerConfig(
    max_failures=2,
    reset_time_seconds=600,     # 10 minutes base
    backoff_multiplier=3,       # Faster progression
    max_backoff_multiplier=16   # Max 2.67 hours
)
```

## Monitoring and Observability

### Health Monitoring

```python
import asyncio
from massgen.mcp_tools.client import MultiMCPClient

async def monitor_circuit_breaker():
    async with MultiMCPClient(server_configs) as client:
        # Access internal circuit breaker
        circuit_breaker = client._circuit_breaker

        while True:
            # Get all failing servers
            failing_servers = circuit_breaker.get_all_failing_servers()

            if failing_servers:
                print("=== Circuit Breaker Status ===")
                for server_name, status in failing_servers.items():
                    print(f"Server: {server_name}")
                    print(f"  Failures: {status['failure_count']}")
                    print(f"  Time remaining: {status['time_remaining']:.1f}s")
                    print(f"  Circuit open: {status['is_circuit_open']}")
                    print()
            else:
                print("All servers healthy")

            await asyncio.sleep(30)  # Check every 30 seconds
```

### Logging Integration

```python
import logging
from massgen.mcp_tools.circuit_breaker import MCPCircuitBreaker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Circuit breaker automatically logs important events:
# - Server failures
# - Circuit opening/closing
# - Recovery events

circuit_breaker = MCPCircuitBreaker()

# Example log output:
# INFO:massgen.mcp_tools.circuit_breaker:Server weather_server failure recorded (1/3)
# WARNING:massgen.mcp_tools.circuit_breaker:Server weather_server has failed 3 times, will be skipped for 300.0 seconds
# INFO:massgen.mcp_tools.circuit_breaker:Circuit breaker reset for server weather_server after 300.0s
# INFO:massgen.mcp_tools.circuit_breaker:Server weather_server recovered after 3 failures
```

## Configuration Examples

### Development Environment

```python
# Lenient configuration for development
dev_config = CircuitBreakerConfig(
    max_failures=5,              # Allow more failures
    reset_time_seconds=30,       # Quick recovery
    backoff_multiplier=1.2,      # Gentle backoff
    max_backoff_multiplier=2     # Short maximum wait
)
```

### Production Environment

```python
# Strict configuration for production
prod_config = CircuitBreakerConfig(
    max_failures=2,              # Fail fast
    reset_time_seconds=300,      # Standard recovery time
    backoff_multiplier=2,        # Standard backoff
    max_backoff_multiplier=8     # Reasonable maximum wait
)
```

### High-Availability Setup

```python
# Configuration for critical systems
ha_config = CircuitBreakerConfig(
    max_failures=1,              # Single failure triggers circuit
    reset_time_seconds=600,      # Longer recovery time
    backoff_multiplier=3,        # Aggressive backoff
    max_backoff_multiplier=16    # Extended maximum wait
)
```

## Troubleshooting

### Common Issues

#### Servers Stuck in Failing State

**Symptoms**: Servers remain in failing state even after underlying issues are resolved.

**Causes**:
- Network issues resolved but circuit breaker hasn't reset
- Clock skew affecting time calculations
- Configuration with very long backoff times

**Solutions**:
```python
# Manual reset
circuit_breaker.reset_all_servers()

# Check server status
failure_count, last_failure, is_open = circuit_breaker.get_server_status("server_name")
print(f"Circuit open: {is_open}, failures: {failure_count}")

# Verify time calculations
import time
current_time = time.monotonic()
time_since_failure = current_time - last_failure
print(f"Time since last failure: {time_since_failure:.1f}s")
```

#### Premature Circuit Opening

**Symptoms**: Circuit opens too quickly for transient failures.

**Causes**:
- `max_failures` set too low
- Transient network issues counted as failures
- Health check too sensitive

**Solutions**:
```python
# Increase failure threshold
config = CircuitBreakerConfig(
    max_failures=5,  # Increased from default 3
    reset_time_seconds=60  # Shorter recovery time
)

# Implement retry logic before recording failure
async def robust_operation(client, circuit_breaker, server_name):
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            result = await client.call_tool("tool_name", {})
            circuit_breaker.record_success(server_name)
            return result
        except Exception as e:
            if attempt == max_retries:
                circuit_breaker.record_failure(server_name)
                raise
            await asyncio.sleep(1)  # Brief retry delay
```

#### Recovery Monitoring Issues

**Symptoms**: Difficulty tracking when servers recover.

**Solutions**:
```python
# Implement recovery monitoring
async def monitor_recovery():
    while True:
        failing_servers = circuit_breaker.get_all_failing_servers()

        for server_name, status in failing_servers.items():
            if status['time_remaining'] <= 0:
                print(f"Server {server_name} ready for retry")

                # Optionally trigger health check
                try:
                    # Attempt connection
                    success = await test_server_connection(server_name)
                    if success:
                        circuit_breaker.record_success(server_name)
                        print(f"Server {server_name} recovered!")
                except Exception:
                    circuit_breaker.record_failure(server_name)

        await asyncio.sleep(10)
```

### Debugging Tips

#### Enable Debug Logging

```python
import logging

# Enable debug logging for circuit breaker
logging.getLogger('massgen.mcp_tools.circuit_breaker').setLevel(logging.DEBUG)

# This will show detailed circuit breaker operations:
# DEBUG:massgen.mcp_tools.circuit_breaker:Server weather_server failure recorded (2/3)
# DEBUG:massgen.mcp_tools.circuit_breaker:Checking circuit breaker for weather_server: 2 failures, 120.5s since last failure
```

#### Status Inspection

```python
# Get detailed circuit breaker state
def inspect_circuit_breaker(circuit_breaker):
    print(f"Circuit breaker: {circuit_breaker}")

    failing_servers = circuit_breaker.get_all_failing_servers()
    if not failing_servers:
        print("No failing servers")
        return

    for server_name, status in failing_servers.items():
        print(f"\nServer: {server_name}")
        print(f"  Failure count: {status['failure_count']}")
        print(f"  Last failure: {status['last_failure_time']}")
        print(f"  Backoff time: {status['backoff_time']:.1f}s")
        print(f"  Time remaining: {status['time_remaining']:.1f}s")
        print(f"  Circuit open: {status['is_circuit_open']}")
```

## Best Practices

### Configuration Guidelines

1. **Development**: Use lenient settings to avoid interrupting development workflow
2. **Testing**: Use moderate settings that allow testing failure scenarios
3. **Production**: Use conservative settings that prioritize system stability
4. **Critical Systems**: Use strict settings with longer backoff times

### Integration Patterns

1. **Always check circuit breaker** before attempting operations on known-failing servers
2. **Record successes** to allow natural recovery
3. **Implement health checks** to proactively detect server recovery
4. **Monitor circuit breaker state** in production environments
5. **Use appropriate logging levels** for different environments

### Error Handling

```python
from massgen.mcp_tools.exceptions import MCPConnectionError, MCPTimeoutError

async def robust_mcp_operation(client, circuit_breaker, server_name):
    # Check circuit breaker first
    if circuit_breaker.should_skip_server(server_name):
        raise MCPConnectionError(
            f"Server {server_name} is currently failing",
            server_name=server_name
        )

    try:
        result = await client.call_tool("tool_name", {})
        circuit_breaker.record_success(server_name)
        return result
    except (MCPConnectionError, MCPTimeoutError) as e:
        # Record failure for connection/timeout errors
        circuit_breaker.record_failure(server_name)
        raise
    except Exception as e:
        # Don't record failure for application-level errors
        logger.warning(f"Application error (not recording failure): {e}")
        raise
```

### Monitoring Integration

```python
# Example Prometheus metrics integration
from prometheus_client import Counter, Gauge, Histogram

# Metrics
circuit_breaker_failures = Counter('mcp_circuit_breaker_failures_total',
                                  'Total circuit breaker failures', ['server'])
circuit_breaker_state = Gauge('mcp_circuit_breaker_open',
                             'Circuit breaker open state', ['server'])
circuit_breaker_backoff = Histogram('mcp_circuit_breaker_backoff_seconds',
                                   'Circuit breaker backoff times', ['server'])

def update_metrics(circuit_breaker):
    failing_servers = circuit_breaker.get_all_failing_servers()

    for server_name, status in failing_servers.items():
        circuit_breaker_failures.labels(server=server_name).inc()
        circuit_breaker_state.labels(server=server_name).set(
            1 if status['is_circuit_open'] else 0
        )
        circuit_breaker_backoff.labels(server=server_name).observe(
            status['backoff_time']
        )
```

## Exception Integration

The circuit breaker works seamlessly with the MCP exception system:

```python
from massgen.mcp_tools.exceptions import (
    MCPConnectionError, MCPTimeoutError, MCPServerError
)

# Circuit breaker automatically handles these exception types:
# - MCPConnectionError: Records failure, triggers circuit breaker
# - MCPTimeoutError: Records failure, triggers circuit breaker
# - MCPServerError: May record failure depending on error type

async def handle_mcp_errors(client, circuit_breaker, server_name):
    try:
        result = await client.call_tool("tool_name", {})
        circuit_breaker.record_success(server_name)
        return result
    except MCPConnectionError as e:
        # Connection failures always trigger circuit breaker
        circuit_breaker.record_failure(server_name)
        e.log_error()  # Use exception's built-in logging
        raise
    except MCPTimeoutError as e:
        # Timeout failures trigger circuit breaker
        circuit_breaker.record_failure(server_name)
        e.log_error()
        raise
    except MCPServerError as e:
        # Server errors may or may not trigger circuit breaker
        if e.http_status and e.http_status >= 500:
            # 5xx errors indicate server problems
            circuit_breaker.record_failure(server_name)
        e.log_error()
        raise
```

This integration ensures that the circuit breaker responds appropriately to different types of failures while maintaining detailed error context through the exception system.