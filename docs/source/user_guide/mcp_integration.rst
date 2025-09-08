MCP Integration
===============

MassGen supports the Model Context Protocol (MCP) for standardized tool integration and agent communication.

What is MCP?
------------

The Model Context Protocol (MCP) is:

* A standard protocol for AI model interactions
* Enables seamless tool integration across platforms
* Provides consistent interfaces for agent capabilities
* Supports both local and remote tool execution

Enabling MCP
------------

Basic Setup
~~~~~~~~~~~

Enable MCP in your MassGen configuration:

.. code-block:: python

   from massgen import Agent, Orchestrator
   from massgen.mcp import MCPServer, MCPClient

   # Start MCP server
   mcp_server = MCPServer(
       port=8765,
       host="localhost",
       auth_token="your-secret-token"
   )
   mcp_server.start()

   # Create MCP-enabled agent
   agent = Agent(
       name="MCPAgent",
       backend=backend,
       mcp_client=MCPClient(
           server_url="http://localhost:8765",
           auth_token="your-secret-token"
       )
   )

MCP Tools
---------

Registering MCP Tools
~~~~~~~~~~~~~~~~~~~~~

Register tools with the MCP server:

.. code-block:: python

   from massgen.mcp import MCPTool

   @mcp_server.register_tool
   class CustomMCPTool(MCPTool):
       name = "custom_tool"
       description = "A custom MCP tool"
       
       def execute(self, params):
           # Tool implementation
           return {"result": "success"}

Using Remote MCP Tools
~~~~~~~~~~~~~~~~~~~~~~

Connect to remote MCP services:

.. code-block:: python

   from massgen.mcp import RemoteMCPClient

   remote_client = RemoteMCPClient(
       server_url="https://mcp.example.com",
       api_key="your-api-key"
   )

   agent = Agent(
       name="RemoteAgent",
       backend=backend,
       mcp_client=remote_client
   )

   # Agent can now use remote MCP tools
   result = agent.run("Use remote translation service")

MCP Communication
-----------------

Agent-to-Agent via MCP
~~~~~~~~~~~~~~~~~~~~~~

Enable direct agent communication through MCP:

.. code-block:: python

   from massgen.mcp import MCPBridge

   # Create MCP bridge for agent communication
   bridge = MCPBridge()

   agent1 = Agent(
       name="Agent1",
       backend=backend1,
       mcp_bridge=bridge
   )

   agent2 = Agent(
       name="Agent2",
       backend=backend2,
       mcp_bridge=bridge
   )

   # Agents can now communicate directly
   orchestrator = Orchestrator(
       agents=[agent1, agent2],
       communication_protocol="mcp"
   )

MCP Messages
~~~~~~~~~~~~

Send and receive MCP messages:

.. code-block:: python

   from massgen.mcp import MCPMessage

   # Send message
   message = MCPMessage(
       type="request",
       content="Analyze this data",
       metadata={"priority": "high"}
   )

   response = agent.send_mcp_message(message, target="Agent2")

   # Handle incoming messages
   @agent.on_mcp_message
   def handle_message(message):
       if message.type == "request":
           return process_request(message)

MCP Tool Discovery
------------------

Automatic Discovery
~~~~~~~~~~~~~~~~~~~

Discover available MCP tools:

.. code-block:: python

   from massgen.mcp import MCPDiscovery

   discovery = MCPDiscovery(
       mcp_client=mcp_client,
       auto_refresh=True,
       refresh_interval=60  # seconds
   )

   # Get available tools
   tools = discovery.get_available_tools()
   for tool in tools:
       print(f"Tool: {tool.name} - {tool.description}")

   # Auto-configure agent with discovered tools
   agent = Agent(
       name="AutoAgent",
       backend=backend,
       tools=discovery.get_tools_for_role("researcher")
   )

Tool Capabilities
~~~~~~~~~~~~~~~~~

Query tool capabilities:

.. code-block:: python

   # Get tool metadata
   tool_info = mcp_client.get_tool_info("web_search")
   print(f"Parameters: {tool_info.parameters}")
   print(f"Returns: {tool_info.return_type}")
   print(f"Rate limit: {tool_info.rate_limit}")

MCP Workflows
-------------

Defining MCP Workflows
~~~~~~~~~~~~~~~~~~~~~~

Create structured workflows with MCP:

.. code-block:: python

   from massgen.mcp import MCPWorkflow

   workflow = MCPWorkflow(
       name="research_workflow",
       steps=[
           {"tool": "web_search", "params": {"query": "{input}"}},
           {"tool": "summarize", "params": {"text": "{step1.result}"}},
           {"tool": "translate", "params": {"text": "{step2.result}", "lang": "es"}}
       ]
   )

   # Register workflow
   mcp_server.register_workflow(workflow)

   # Use workflow in agent
   agent = Agent(
       name="WorkflowAgent",
       backend=backend,
       workflows=[workflow]
   )

   result = agent.run_workflow("research_workflow", input="quantum computing")

Workflow Orchestration
~~~~~~~~~~~~~~~~~~~~~~

Orchestrate complex MCP workflows:

.. code-block:: python

   from massgen.mcp import WorkflowOrchestrator

   orchestrator = WorkflowOrchestrator(
       mcp_server=mcp_server,
       parallel_execution=True,
       max_concurrent=5
   )

   # Define complex workflow
   complex_workflow = {
       "name": "data_pipeline",
       "stages": [
           {
               "name": "collect",
               "parallel": True,
               "tools": ["scraper", "api_fetcher", "db_query"]
           },
           {
               "name": "process",
               "tools": ["cleaner", "transformer"]
           },
           {
               "name": "analyze",
               "tools": ["ml_model", "statistical_analysis"]
           }
       ]
   }

   result = orchestrator.execute_workflow(complex_workflow)

MCP Security
------------

Authentication
~~~~~~~~~~~~~~

Implement MCP authentication:

.. code-block:: python

   from massgen.mcp import MCPAuth

   auth = MCPAuth(
       method="oauth2",  # or "api_key", "jwt"
       client_id="your-client-id",
       client_secret="your-client-secret",
       token_endpoint="https://auth.example.com/token"
   )

   mcp_client = MCPClient(
       server_url="https://mcp.example.com",
       auth=auth
   )

Encryption
~~~~~~~~~~

Enable end-to-end encryption:

.. code-block:: python

   from massgen.mcp import MCPEncryption

   encryption = MCPEncryption(
       algorithm="AES-256-GCM",
       key_exchange="ECDH",
       public_key="..."
   )

   secure_client = MCPClient(
       server_url="https://mcp.example.com",
       encryption=encryption
   )

MCP Monitoring
--------------

Logging and Metrics
~~~~~~~~~~~~~~~~~~~

Monitor MCP operations:

.. code-block:: python

   from massgen.mcp import MCPMonitor

   monitor = MCPMonitor(
       log_level="INFO",
       metrics_enabled=True,
       trace_requests=True
   )

   mcp_server = MCPServer(
       port=8765,
       monitor=monitor
   )

   # Access metrics
   metrics = monitor.get_metrics()
   print(f"Total requests: {metrics['total_requests']}")
   print(f"Average latency: {metrics['avg_latency_ms']}")

Health Checks
~~~~~~~~~~~~~

Implement MCP health checks:

.. code-block:: python

   from massgen.mcp import MCPHealthCheck

   health_check = MCPHealthCheck(
       interval=30,  # seconds
       timeout=5,
       failure_threshold=3
   )

   mcp_client = MCPClient(
       server_url="https://mcp.example.com",
       health_check=health_check
   )

   # Check health status
   if mcp_client.is_healthy():
       result = agent.run("Execute task")

Advanced MCP Features
---------------------

MCP Plugins
~~~~~~~~~~~

Create and use MCP plugins:

.. code-block:: python

   from massgen.mcp import MCPPlugin

   class CustomPlugin(MCPPlugin):
       def on_request(self, request):
           # Modify request before sending
           request.headers["X-Custom"] = "value"
           return request
       
       def on_response(self, response):
           # Process response
           return response

   mcp_client = MCPClient(
       server_url="https://mcp.example.com",
       plugins=[CustomPlugin()]
   )

MCP Federation
~~~~~~~~~~~~~~

Connect multiple MCP servers:

.. code-block:: python

   from massgen.mcp import MCPFederation

   federation = MCPFederation([
       MCPServer(port=8765, name="server1"),
       MCPServer(port=8766, name="server2"),
       MCPServer(port=8767, name="server3")
   ])

   # Tools are available across all servers
   agent = Agent(
       name="FederatedAgent",
       backend=backend,
       mcp_federation=federation
   )

Best Practices
--------------

1. **Version Management**: Always specify MCP protocol version
2. **Error Handling**: Implement robust error handling for network issues
3. **Caching**: Cache tool discovery results
4. **Security**: Always use authentication and encryption in production
5. **Monitoring**: Monitor MCP performance and availability
6. **Documentation**: Document custom MCP tools and workflows
7. **Testing**: Test MCP integrations thoroughly

Next Steps
----------

* :doc:`advanced_usage` - Advanced MCP patterns
* :doc:`../api/index` - MCP API reference
* :doc:`../examples/basic_examples` - MCP usage examples