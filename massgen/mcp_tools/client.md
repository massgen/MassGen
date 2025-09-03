# MCP Client Documentation

## Overview

The MCP client module provides the core functionality for connecting to and interacting with MCP (Model Context Protocol) servers. It includes two main classes: `MCPClient` for single-server connections and `MultiMCPClient` for managing multiple servers simultaneously.

## Client Architecture

The client architecture follows an async-first design with comprehensive error handling and security validation:

- **Connection Lifecycle**: Automatic connection management with reconnection capabilities
- **Security Integration**: Built-in validation using the security module
- **Circuit Breaker**: Automatic failure detection and recovery
- **Resource Management**: Proper cleanup and connection pooling

## MCPClient Class

The `MCPClient` class handles connections to individual MCP servers and provides methods for tool execution, resource access, and server management.

### Initialization

```python
from massgen.mcp_tools import MCPClient

# Basic configuration
config = {
    "name": "test_server",
    "type": "stdio",
    "command": "python",
    "args": ["-m", "massgen.tests.mcp_test_server"],
    "security": {
        "level": "moderate"
    },
    "timeout": 30,
    "max_retries": 3
}

client = MCPClient(config)
```

### Connection Management

#### connect()

**What it does**: This function establishes a connection to an MCP server. Think of it like dialing a phone number - it sets up the communication channel so you can start using the server's tools.

**Why you need it**: Before you can use any tools from an MCP server, you need to connect to it first. This function handles all the technical details of establishing that connection.

**What happens when you call it**:

1. Validates your configuration for security
2. Starts the MCP server process (for stdio) or connects to the web server (for HTTP)
3. Performs a "handshake" to establish communication
4. Discovers what tools, resources, and prompts are available
5. Sets up the connection for use

```python
async def connect_example():
    config = {
        "name": "my_server",
        "type": "stdio",
        "command": "python",
        "args": ["-m", "my_mcp_server"]
    }

    # Method 1: Using async context manager (recommended)
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        print("✅ Connected successfully!")

        # Use the client here...
        tools = client.get_available_tools()
        print(f"Available tools: {tools}")

        # Connection automatically closed when exiting the 'with' block

    # Method 2: Manual connection management
    client = MCPClient(config)
    try:
        await client.connect()
        print("✅ Connected successfully!")

        # Use the client...

    finally:
        await client.disconnect()  # Always disconnect when done
```

#### disconnect()

**What it does**: Safely closes the connection to the MCP server. Like hanging up a phone call, it properly ends the communication and cleans up resources.

**Why you need it**: Always disconnect when you're done to free up system resources and ensure the server process is properly terminated.

**What happens when you call it**:

1. Signals the server that you're disconnecting
2. Closes the communication channel
3. Terminates the server process (for stdio servers)
4. Cleans up memory and file handles
5. Resets the client state

```python
async def manual_connection():
    client = MCPClient(config)
    try:
        await client.connect()
        print("✅ Connected to server")

        # Do your work here...
        result = await client.call_tool("some_tool", {})

    except Exception as e:
        print(f"❌ Error occurred: {e}")
    finally:
        # ALWAYS disconnect, even if errors occurred
        await client.disconnect()
        print("✅ Disconnected safely")

# ✅ Better approach - use context manager (auto-disconnect)
async def recommended_approach():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        # Work with client...
        # Automatic disconnect happens here, even if errors occur
```

#### reconnect()

**What it does**: If the connection to the MCP server is lost or broken, this function tries to reconnect automatically. It's smart about retrying - it waits longer between each attempt to avoid overwhelming a struggling server.

**Why you need it**: Network connections can fail, servers can crash, or temporary issues can break the connection. Instead of giving up, this function tries to restore the connection.

**Parameters**:

- `max_retries`: How many times to try reconnecting (default: 3)
- `retry_delay`: How long to wait between attempts in seconds (default: 1.0)

**Returns**: True if reconnection succeeded, False if all attempts failed

```python
async def reconnect_example():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        print("✅ Initial connection established")

        # Simulate using the client
        try:
            result = await client.call_tool("some_tool", {})
            print(f"Tool result: {result}")

        except MCPConnectionError as e:
            print(f"❌ Connection lost: {e}")

            # Try to reconnect
            print("🔄 Attempting to reconnect...")
            success = await client.reconnect(max_retries=5, retry_delay=2.0)

            if success:
                print("✅ Reconnected successfully!")
                # Try the tool again
                result = await client.call_tool("some_tool", {})
                print(f"Tool result after reconnect: {result}")
            else:
                print("❌ Failed to reconnect after 5 attempts")

# ✅ Automatic reconnection with health checks
async def robust_client_usage():
    # The async context manager connects automatically
    async with MCPClient(config) as client:

        # Check if connection is healthy before important operations
        if not await client.health_check():
            print("⚠️ Connection seems unhealthy, attempting reconnect...")
            await client.reconnect()

        # Now proceed with confidence
        result = await client.call_tool("important_tool", {"data": "value"})
```

### Tool Operations

#### call_tool()

**What it does**: This is the main function you'll use to actually run tools on the MCP server. It's like calling a function on a remote computer - you provide the tool name and arguments, and get back the result.

**Why you need it**: This is how you actually use the MCP server's capabilities. Whether you want to read files, process data, or perform any other task, you do it through this function.

**Parameters**:

- `tool_name` (required): The name of the tool you want to run (e.g., "read_file")
- `arguments` (required): Dictionary of parameters the tool needs (e.g., {"path": "file.txt"})

**Returns**: The result from the tool (could be text, data, or complex objects)

**What happens when you call it**:

1. Validates that the tool exists on the server
2. Checks that your arguments are safe and valid
3. Sends the request to the MCP server
4. Waits for the server to process it
5. Returns the result or raises an error if something went wrong

```python
async def tool_execution():
    # The async context manager connects automatically
    async with MCPClient(config) as client:

        # ✅ Simple tool call - like calling a function
        result = await client.call_tool("echo", {"message": "Hello World"})
        print(f"Echo result: {result}")
        # Output: "Hello World" (or whatever the echo tool returns)

        # ✅ Tool call with multiple arguments
        file_result = await client.call_tool("read_file", {
            "path": "/safe/path/document.txt",
            "encoding": "utf-8",
            "max_lines": 100
        })
        print(f"File contents: {file_result}")

        # ✅ Tool call with complex data
        analysis_result = await client.call_tool("analyze_data", {
            "data": [1, 2, 3, 4, 5],
            "options": {
                "method": "statistical",
                "include_graphs": True
            }
        })
        print(f"Analysis: {analysis_result}")

        # ❌ Handle common errors gracefully
        try:
            # Tool doesn't exist
            result = await client.call_tool("nonexistent_tool", {})
        except MCPError as e:
            print(f"❌ Tool not found: {e}")
            # Show available tools to help user
            available = client.get_available_tools()
            print(f"Available tools: {available}")

        try:
            # Wrong arguments
            result = await client.call_tool("read_file", {"wrong_param": "value"})
        except MCPValidationError as e:
            print(f"❌ Invalid arguments: {e}")

        try:
            # Server error
            result = await client.call_tool("buggy_tool", {})
        except MCPServerError as e:
            print(f"❌ Server error: {e}")

        try:
            # Timeout
            result = await client.call_tool("slow_tool", {"timeout": 1})
        except MCPTimeoutError as e:
            print(f"❌ Tool took too long: {e}")

# ✅ Best practices for tool calls
async def best_practices():
    # The async context manager connects automatically
    async with MCPClient(config) as client:

        # 1. Always check if tool exists first
        available_tools = client.get_available_tools()
        if "my_tool" not in available_tools:
            print("❌ Tool not available")
            return

        # 2. Use try-catch for error handling
        try:
            result = await client.call_tool("my_tool", {"param": "value"})
            print(f"✅ Success: {result}")
        except Exception as e:
            print(f"❌ Error: {e}")

        # 3. Validate your arguments match what the tool expects
        # (Check tool documentation or use get_available_tools() for details)
```

#### Tool Discovery

**What it does**: Gets detailed information about all the tools available on the MCP server. You can use `client.get_available_tools()` for tool names. For detailed metadata, note that `client.session` is internal and subject to change - use the public API when possible.

**Why you need it**: Before you can use tools, you need to know what's available and how to use them. These functions give you that information.

**Returns**: List of tool names (get_available_tools) or detailed tool objects (internal session access)

```python
async def discover_tools():
    # The async context manager connects automatically
    async with MCPClient(config) as client:

        # Get detailed information about all tools
        # Note: session access is internal and may change
        tools = await client.session.list_tools()

        print(f"📋 Found {len(tools.tools)} tools on this server:")
        print()

        for tool in tools.tools:
            print(f"🔧 Tool: {tool.name}")
            print(f"   Description: {tool.description}")

            # Show what parameters this tool accepts
            if hasattr(tool, 'inputSchema') and tool.inputSchema:
                print(f"   Parameters: {tool.inputSchema.get('properties', {})}")

            print()  # Empty line for readability

# ✅ Practical example - exploring a file server
async def explore_file_server():
    # The async context manager connects automatically
    async with MCPClient(config) as client:

        # Note: session access is internal and may change
        tools = await client.session.list_tools()

        # Look for file-related tools
        file_tools = [tool for tool in tools.tools if 'file' in tool.name.lower()]

        print("📁 File-related tools:")
        for tool in file_tools:
            print(f"  • {tool.name}: {tool.description}")

        # Show how to use a specific tool
        if file_tools:
            example_tool = file_tools[0]
            print(f"\n📖 How to use '{example_tool.name}':")
            print(f"   await client.call_tool('{example_tool.name}', {{...}})")

            if hasattr(example_tool, 'inputSchema') and example_tool.inputSchema:
                print(f"   Required parameters: {example_tool.inputSchema.get('properties', {})}")

# ✅ Simple way to just get tool names
async def get_tool_names():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        # Quick way to get just the names
        tool_names = client.get_available_tools()
        print(f"Available tools: {tool_names}")

        # Check if a specific tool exists
        if "read_file" in tool_names:
            print("✅ File reading is available")
        else:
            print("❌ No file reading capability")
```

### Resource Operations

#### get_resource()

**What it does**: Retrieves data or files from the MCP server using a URI (address). Resources are like files or data sources that the server makes available - they could be configuration files, databases, web content, or any other data.

**Why you need it**: Some MCP servers provide access to data sources beyond just tools. For example, a server might provide access to configuration files, documentation, or cached data.

**Parameters**:

- `uri` (required): The resource address (e.g., "file:///config.json", "http://api/data")

**Returns**: Resource content (format depends on the resource type)

```python
from massgen.mcp_tools.exceptions import MCPServerError
# Optionally import mcp_types for type hints
# from mcp import types as mcp_types

async def resource_access():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        # ✅ Get a configuration file
        try:
            config_resource = await client.get_resource("file:///app/config.json")
            # Returns ReadResourceResult with contents
            print(f"Config content: {config_resource.contents}")
        except MCPServerError as e:
            print(f"❌ Could not load config: {e}")

        # ✅ Get web-based data
        try:
            api_data = await client.get_resource("http://internal-api/status")
            print(f"API status: {api_data.contents}")
        except MCPServerError as e:
            print(f"❌ API not accessible: {e}")

        # ✅ List all available resources first
        available_resources = client.get_available_resources()
        print(f"📋 Available resources:")
        for uri in available_resources:
            print(f"  • {uri}")

        # ✅ Access each available resource
        for uri in available_resources:
            try:
                resource = await client.get_resource(uri)
                print(f"✅ {uri}: {len(str(resource.contents))} characters")
            except Exception as e:
                print(f"❌ {uri}: Failed to load - {e}")
```

#### get_prompt()

**What it does**: Gets a pre-written text template from the server and fills it in with your data. Prompts are like form letters - they have placeholders that get replaced with your specific information.

**Why you need it**: Many MCP servers provide useful prompt templates for common tasks like code reviews, text summaries, or translations. Instead of writing these prompts yourself, you can use the server's templates.

**Parameters**:

- `name` (required): The name of the prompt template (e.g., "code_review")
- `arguments` (optional): Dictionary of values to fill in the template

**Returns**: Prompt object with the generated text

```python
from massgen.mcp_tools.exceptions import MCPServerError
# Optionally import mcp_types for type hints
# from mcp import types as mcp_types

async def prompt_usage():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        # ✅ Use a code review prompt
        try:
            review_prompt = await client.get_prompt("code_review", {
                "language": "python",
                "code": "def hello():\n    print('world')",
                "focus": "best_practices"
            })
            # Returns GetPromptResult with messages
            print(f"📝 Generated review prompt:")
            print(review_prompt.messages)
        except MCPServerError as e:
            print(f"❌ Prompt not available: {e}")

        # ✅ Use a translation prompt
        try:
            translate_prompt = await client.get_prompt("translate", {
                "text": "Hello, how are you?",
                "from_language": "english",
                "to_language": "spanish"
            })
            print(f"🌍 Translation prompt: {translate_prompt.messages}")
        except MCPServerError as e:
            print(f"❌ Translation prompt failed: {e}")

        # ✅ List available prompts first
        available_prompts = client.get_available_prompts()
        print(f"📋 Available prompts: {available_prompts}")

        # ✅ Use prompts dynamically
        for prompt_name in available_prompts:
            try:
                # Try with minimal arguments
                prompt = await client.get_prompt(prompt_name, {})
                print(f"✅ {prompt_name}: Template loaded")
            except Exception as e:
                print(f"❌ {prompt_name}: Needs specific arguments - {e}")
```

### Health and Monitoring

#### health_check()

**What it does**: Tests if the connection to the MCP server is still working properly. It's like pinging a server to see if it's still alive and responding.

**Why you need it**: Network connections can become unstable, servers can become overloaded, or processes can crash. This function helps you detect these problems before they cause your tools to fail.

**Returns**: True if the server is healthy and responding, False if there are problems

**What it checks**:

1. Is the connection still active?
2. Can the server respond to basic requests?
3. Are the server's core functions working?

```python
async def monitor_health():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        # ✅ Basic health check
        is_healthy = await client.health_check()
        if is_healthy:
            print("✅ Server is healthy and responding")
        else:
            print("❌ Server health check failed")

        # ✅ Use health check before important operations
        if await client.health_check():
            # Safe to proceed
            result = await client.call_tool("important_tool", {"data": "value"})
        else:
            print("⚠️ Server unhealthy, attempting reconnect...")
            success = await client.reconnect()
            if success:
                result = await client.call_tool("important_tool", {"data": "value"})
            else:
                print("❌ Could not restore connection")

# ✅ Continuous health monitoring
async def continuous_monitoring():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        import asyncio

        # Check health every 30 seconds
        while True:
            try:
                if await client.health_check():
                    print("✅ Health check passed")
                else:
                    print("⚠️ Health check failed, reconnecting...")
                    await client.reconnect()

                # Wait 30 seconds before next check
                await asyncio.sleep(30)

            except KeyboardInterrupt:
                print("Stopping health monitoring")
                break
            except Exception as e:
                print(f"❌ Health monitoring error: {e}")
                await asyncio.sleep(5)  # Wait before retrying

# ✅ Health check with timeout
async def quick_health_check():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        try:
            # Set a short timeout for health check
            health_task = asyncio.create_task(client.health_check())
            is_healthy = await asyncio.wait_for(health_task, timeout=5.0)

            if is_healthy:
                print("✅ Server responded quickly")
            else:
                print("❌ Server is slow or unresponsive")

        except asyncio.TimeoutError:
            print("❌ Health check timed out - server is very slow")
        except Exception as e:
            print(f"❌ Health check error: {e}")
```

### Utility Functions

#### get_available_tools()

**What it does**: Returns a simple list of tool names available on the server. This is a quick way to see what tools you can use without getting detailed information.

**Returns**: List of strings (tool names)

```python
# The async context manager connects automatically
async with MCPClient(config) as client:
    # Get just the tool names
    tools = client.get_available_tools()
    print(f"Available tools: {tools}")
    # Output: ['read_file', 'write_file', 'list_directory', 'search_text']

    # Check if a specific tool exists
    if 'read_file' in tools:
        print("✅ Can read files")
```

#### get_available_resources()

**What it does**: Returns a list of resource URIs (addresses) that you can access on the server. Resources are like files or data sources that the server can provide.

**Returns**: List of strings (resource URIs)

```python
# The async context manager connects automatically
async with MCPClient(config) as client:
    # Get available resources
    resources = client.get_available_resources()
    print(f"Available resources: {resources}")
    # Output: ['file:///config.json', 'http://api/data', 'memory://cache']
```

#### get_available_prompts()

**What it does**: Returns a list of prompt templates available on the server. Prompts are pre-written text templates that can be customized with your data.

**Returns**: List of strings (prompt names)

```python
# The async context manager connects automatically
async with MCPClient(config) as client:
    # Get available prompts
    prompts = client.get_available_prompts()
    print(f"Available prompts: {prompts}")
    # Output: ['code_review', 'summarize_text', 'translate']
```

#### is_connected()

**What it does**: Checks if the client is currently connected to the MCP server. This is useful for verifying the connection status before trying to use tools.

**Returns**: True if connected, False if not connected

```python
# The async context manager connects automatically
async with MCPClient(config) as client:
    # After automatic connection
    print(f"Connected: {client.is_connected()}")  # True

    # Use in conditional logic
    if client.is_connected():
        result = await client.call_tool("some_tool", {})
    else:
        print("❌ Not connected - cannot use tools")
        await client.connect()
```

## MultiMCPClient Class

The `MultiMCPClient` class manages connections to multiple MCP servers simultaneously, providing unified access to tools and resources across all connected servers.

### Initialization and Connection

#### MultiMCPClient()

Creates a MultiMCPClient instance and connects to multiple MCP servers based on configuration.

```python
from massgen.mcp_tools import MultiMCPClient

async def multi_server_setup():
    # Configuration for multiple servers - use list format
    servers_config = [
        {
            "name": "file_server",
            "type": "stdio",
            "command": "python",
            "args": ["-m", "file_mcp_server"],
            "security": {
                "level": "strict"
            }
        },
        {
            "name": "web_server",
            "type": "streamable-http",
            "url": "http://localhost:8000/mcp",
            "security": {
                "level": "moderate"
            }
        }
    ]

    # Create and connect to all servers
    multi_client = MultiMCPClient(servers_config)
    await multi_client.connect()

    # Alternative: Transform dict format using validator
    # from massgen.mcp_tools import MCPConfigValidator
    # dict_config = {"server1": {...}, "server2": {...}}
    # validated_config = MCPConfigValidator.validate_backend_mcp_config(dict_config)
    # multi_client = MultiMCPClient(validated_config)
    # await multi_client.connect()

    try:
        # Use the multi-client
        tools = list(multi_client.tools.keys())
        print(f"Total tools available: {len(tools)}")
    finally:
        await multi_client.disconnect()
```

### Tool Routing

Tools in multi-server setups are prefixed with the server name for disambiguation.

```python
async def multi_server_tools():
    multi_client = MultiMCPClient(servers_config)
    await multi_client.connect()

    try:
        # Call tool from specific server
        file_result = await multi_client.call_tool("mcp__file_server__read_file", {
            "path": "example.txt"
        })

        web_result = await multi_client.call_tool("mcp__web_server__fetch_url", {
            "url": "https://api.example.com/data"
        })

        # List tools by server - filter by server prefix
        file_tools = [t for t in multi_client.tools if t.startswith("mcp__file_server__")]
        web_tools = [t for t in multi_client.tools if t.startswith("mcp__web_server__")]

    finally:
        await multi_client.disconnect()
```

### Circuit Breaker Integration

The multi-client includes circuit breaker functionality for handling server failures.

```python
async def circuit_breaker_example():
    # Configuration with circuit breaker settings
    config_with_cb = [
        {
            "name": "file_server",
            "type": "stdio",
            "command": "python",
            "args": ["-m", "unreliable_server"],
            "circuit_breaker": {
                "failure_threshold": 5,
                "recovery_timeout": 60,
                "expected_exception": "MCPConnectionError"
            }
        }
    ]

    multi_client = MultiMCPClient(config_with_cb)
    await multi_client.connect()

    try:
        # Circuit breaker will handle failures automatically
        for i in range(10):
            try:
                result = await multi_client.call_tool("mcp__file_server__unstable_tool", {})
                print(f"Success: {result}")
            except Exception as e:
                print(f"Handled by circuit breaker: {e}")

    finally:
        await multi_client.disconnect()
```

## Configuration Integration

### Config Validator Integration

The client integrates with the config validator for comprehensive validation.

```python
from massgen.mcp_tools import MCPConfigValidator, validate_mcp_integration

async def validated_client():
    # Raw configuration
    raw_config = {
        "type": "streamable-http",
        "url": "http://localhost:8000/mcp",
        "timeout": "invalid_timeout"  # This will be caught
    }

    try:
        # Validate configuration before creating client
        validated_config = MCPConfigValidator.validate_server_config(raw_config)
        client = MCPClient(validated_config)
        await client.connect()
    except MCPConfigurationError as e:
        print(f"Configuration error: {e}")
```

### Timeout Configuration

Configure timeouts for different operations:

```python
config_with_timeouts = {
    "name": "slow_server",
    "type": "stdio",
    "command": "python",
    "args": ["-m", "slow_server"],
    "timeout": 60,  # General timeout
    "http_read_timeout": 300  # HTTP read timeout for streamable-http transport
}
```

## Practical Examples

### Example 1: File Processing Server

```python
# Based on massgen/configs/gemini_mcp_example.yaml
async def file_processing_example():
    config = {
        "name": "file_processor",
        "type": "stdio",
        "command": "python",
        "args": ["-m", "file_processor_server"],
        "security": {
            "level": "strict"
        },
        "timeout": 30
    }

    # The async context manager connects automatically
    async with MCPClient(config) as client:
        # Process multiple files
        files = ["doc1.txt", "doc2.txt", "doc3.txt"]
        results = []

        for file_path in files:
            try:
                result = await client.call_tool("process_file", {
                    "path": file_path,
                    "operation": "analyze"
                })
                results.append(result)
            except MCPServerError as e:
                print(f"Failed to process {file_path}: {e}")

        return results
```

### Example 2: Multi-Server Coordination

```python
# Based on massgen/configs/claude_code_discord_mcp_example.yaml
async def multi_server_coordination():
    servers_config = [
        {
            "name": "code_analyzer",
            "type": "stdio",
            "command": "python",
            "args": ["-m", "code_analysis_server"],
            "security": {
                "level": "moderate"
            }
        },
        {
            "name": "discord_bot",
            "type": "streamable-http",
            "url": "http://localhost:8001/mcp",
            "headers": {"Authorization": "Bearer discord-token"},
            "security": {
                "level": "strict"
            }
        }
    ]

    multi_client = MultiMCPClient(servers_config)
    await multi_client.connect()

    try:
        # Analyze code
        analysis = await multi_client.call_tool("mcp__code_analyzer__analyze_python", {
            "file_path": "main.py"
        })

        # Send results to Discord
        await multi_client.call_tool("mcp__discord_bot__send_message", {
            "channel": "code-reviews",
            "content": f"Analysis complete: {analysis['summary']}"
        })

    finally:
        await multi_client.disconnect()
```

## Best Practices

### Error Handling

Always use proper exception handling with specific exception types:

```python
from massgen.mcp_tools.exceptions import (
    MCPConnectionError, MCPServerError, MCPConfigurationError,
    MCPTimeoutError, MCPValidationError
)

async def robust_client_usage():
    # The async context manager connects automatically
    async with MCPClient(config) as client:
        try:
            result = await client.call_tool("example_tool", args)

        except MCPConnectionError:
            # Handle connection issues
            await client.reconnect()

        except MCPServerError as e:
            # Handle tool-specific errors
            print(f"Tool failed: {e}")

        except MCPConfigurationError as e:
            # Handle configuration validation failures
            print(f"Configuration error: {e}")

        except MCPTimeoutError:
            # Handle timeouts
            print("Operation timed out")
```

### Connection Pooling

For high-throughput applications, consider connection pooling:

```python
class MCPConnectionPool:
    def __init__(self, config, pool_size=5):
        self.config = config
        self.pool_size = pool_size
        self.connections = []

    async def get_connection(self):
        if self.connections:
            return self.connections.pop()
        return MCPClient(self.config)

    async def return_connection(self, client):
        if len(self.connections) < self.pool_size:
            self.connections.append(client)
        else:
            await client.disconnect()
```

### Resource Cleanup

Always ensure proper resource cleanup:

```python
async def proper_cleanup():
    client = None
    try:
        client = MCPClient(config)
        await client.connect()
        # ... operations
    finally:
        if client:
            await client.disconnect()
```

## Integration with MassGen

The MCP client integrates seamlessly with MassGen's orchestration system:

```python
from massgen.orchestrator import MassGenOrchestrator

async def massgen_integration():
    # MassGen automatically manages MCP clients based on configuration
    orchestrator = MassGenOrchestrator(config_path="config.yaml")

    # MCP tools are available through the orchestrator
    result = await orchestrator.execute_task({
        "task": "analyze_code",
        "mcp_tools": ["mcp__code_analyzer__lint", "mcp__code_analyzer__security_scan"]
    })
```

This integration allows MassGen to automatically discover and use MCP tools as part of its task execution pipeline.
