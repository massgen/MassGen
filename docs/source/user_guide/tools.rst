Tools
=====

Tools extend agent capabilities beyond text generation, enabling them to interact with external systems and perform specialized tasks.

Overview
--------

Tools in MassGen:

* Provide specific capabilities to agents
* Are executed when agents need them
* Can be chained together for complex tasks
* Support both synchronous and asynchronous execution

Built-in Tools
--------------

Web Search
~~~~~~~~~~

Enable agents to search the internet:

.. code-block:: python

   from massgen.tools import WebSearch

   search_tool = WebSearch(
       api_key="your-search-api-key",  # Optional
       max_results=10,
       safe_search=True,
       region="us"
   )

   agent = Agent(
       name="ResearchAgent",
       backend=backend,
       tools=[search_tool]
   )

   # Agent can now search when needed
   result = agent.run("Find the latest developments in quantum computing")

Calculator
~~~~~~~~~~

Perform mathematical calculations:

.. code-block:: python

   from massgen.tools import Calculator

   calc_tool = Calculator(
       precision=10,
       scientific_mode=True,
       symbolic_math=False
   )

   agent = Agent(
       name="MathAgent",
       backend=backend,
       tools=[calc_tool]
   )

   result = agent.run("Calculate the compound interest on $10,000 at 5% for 10 years")

File Operations
~~~~~~~~~~~~~~~

Read and write files:

.. code-block:: python

   from massgen.tools import FileReader, FileWriter

   reader = FileReader(
       allowed_extensions=[".txt", ".md", ".json"],
       max_file_size=10_000_000  # 10MB
   )

   writer = FileWriter(
       output_directory="./outputs",
       create_directories=True
   )

   agent = Agent(
       name="FileAgent",
       backend=backend,
       tools=[reader, writer]
   )

Database Query
~~~~~~~~~~~~~~

Execute database queries:

.. code-block:: python

   from massgen.tools import DatabaseQuery

   db_tool = DatabaseQuery(
       connection_string="postgresql://user:pass@localhost/db",
       read_only=True,
       timeout=30
   )

   agent = Agent(
       name="DataAgent",
       backend=backend,
       tools=[db_tool]
   )

   result = agent.run("Find all users who registered last month")

API Integration
~~~~~~~~~~~~~~~

Call external APIs:

.. code-block:: python

   from massgen.tools import APICall

   api_tool = APICall(
       base_url="https://api.example.com",
       headers={"Authorization": "Bearer token"},
       timeout=30,
       retry_count=3
   )

   agent = Agent(
       name="APIAgent",
       backend=backend,
       tools=[api_tool]
   )

Code Execution
~~~~~~~~~~~~~~

Execute code safely:

.. code-block:: python

   from massgen.tools import CodeExecutor

   code_tool = CodeExecutor(
       languages=["python", "javascript"],
       sandbox=True,
       timeout=10,
       memory_limit="512MB"
   )

   agent = Agent(
       name="CodingAgent",
       backend=backend,
       tools=[code_tool]
   )

Creating Custom Tools
---------------------

Basic Tool Structure
~~~~~~~~~~~~~~~~~~~~

Create your own tools:

.. code-block:: python

   from massgen.tools import Tool
   from typing import Any, Dict

   class CustomTool(Tool):
       def __init__(self, **kwargs):
           super().__init__(**kwargs)
           self.name = "CustomTool"
           self.description = "Description of what this tool does"
       
       def execute(self, *args, **kwargs) -> Any:
           """Execute the tool's functionality"""
           # Your implementation here
           result = self._perform_operation(args, kwargs)
           return result
       
       def validate_input(self, *args, **kwargs) -> bool:
           """Validate input before execution"""
           # Input validation logic
           return True

Advanced Tool Example
~~~~~~~~~~~~~~~~~~~~~

A weather information tool:

.. code-block:: python

   import requests
   from massgen.tools import Tool

   class WeatherTool(Tool):
       def __init__(self, api_key: str):
           super().__init__()
           self.name = "WeatherTool"
           self.description = "Get current weather information"
           self.api_key = api_key
           self.base_url = "https://api.weather.com/v1"
       
       def execute(self, location: str) -> Dict:
           """Get weather for a location"""
           if not self.validate_input(location):
               raise ValueError("Invalid location")
           
           response = requests.get(
               f"{self.base_url}/current",
               params={"location": location, "key": self.api_key}
           )
           
           if response.status_code == 200:
               return response.json()
           else:
               raise Exception(f"Weather API error: {response.status_code}")
       
       def validate_input(self, location: str) -> bool:
           """Validate location input"""
           return bool(location and isinstance(location, str))

Tool Composition
----------------

Chaining Tools
~~~~~~~~~~~~~~

Chain tools for complex operations:

.. code-block:: python

   from massgen.tools import ToolChain

   chain = ToolChain([
       WebSearch(),
       DataExtractor(),
       Summarizer(),
       FileWriter()
   ])

   agent = Agent(
       name="ChainAgent",
       backend=backend,
       tools=[chain]
   )

   # Tools execute in sequence
   result = agent.run("Research and summarize latest AI trends, save to file")

Conditional Tools
~~~~~~~~~~~~~~~~~

Use tools conditionally:

.. code-block:: python

   from massgen.tools import ConditionalTool

   conditional_tool = ConditionalTool(
       tool=ExpensiveTool(),
       condition=lambda context: context.get("use_expensive", False)
   )

   agent = Agent(
       name="ConditionalAgent",
       backend=backend,
       tools=[conditional_tool]
   )

Tool Configuration
------------------

Tool Parameters
~~~~~~~~~~~~~~~

Configure tool behavior:

.. code-block:: python

   tool = WebSearch(
       # Authentication
       api_key="...",
       
       # Behavior
       max_results=10,
       timeout=30,
       
       # Filtering
       safe_search=True,
       language="en",
       region="us",
       
       # Caching
       cache_results=True,
       cache_ttl=3600
   )

Tool Permissions
~~~~~~~~~~~~~~~~

Control tool access:

.. code-block:: python

   from massgen.tools import ToolPermissions

   permissions = ToolPermissions(
       read_files=True,
       write_files=False,
       network_access=True,
       execute_code=False
   )

   tool = FileReader(permissions=permissions)

Asynchronous Tools
------------------

Async Tool Implementation
~~~~~~~~~~~~~~~~~~~~~~~~~

Create asynchronous tools:

.. code-block:: python

   import asyncio
   from massgen.tools import AsyncTool

   class AsyncWebScraper(AsyncTool):
       async def execute_async(self, url: str) -> str:
           """Asynchronously scrape a webpage"""
           async with aiohttp.ClientSession() as session:
               async with session.get(url) as response:
                   return await response.text()

   # Use with async agents
   agent = Agent(
       name="AsyncAgent",
       backend=backend,
       tools=[AsyncWebScraper()],
       async_mode=True
   )

Parallel Tool Execution
~~~~~~~~~~~~~~~~~~~~~~~~

Execute multiple tools in parallel:

.. code-block:: python

   from massgen.tools import ParallelTools

   parallel_tools = ParallelTools([
       WebSearch(),
       DatabaseQuery(),
       APICall()
   ])

   agent = Agent(
       name="ParallelAgent",
       backend=backend,
       tools=[parallel_tools]
   )

   # Tools execute simultaneously
   result = agent.run("Gather data from multiple sources")

Tool Monitoring
---------------

Logging Tool Usage
~~~~~~~~~~~~~~~~~~

Monitor tool execution:

.. code-block:: python

   from massgen.tools import ToolMonitor

   monitor = ToolMonitor(
       log_level="INFO",
       track_usage=True,
       track_performance=True
   )

   tool = WebSearch(monitor=monitor)

   # Access usage statistics
   stats = monitor.get_statistics()
   print(f"Total calls: {stats['total_calls']}")
   print(f"Average duration: {stats['avg_duration']}")

Tool Metrics
~~~~~~~~~~~~

Collect tool metrics:

.. code-block:: python

   from massgen.tools import MetricsCollector

   metrics = MetricsCollector()

   tool = Calculator(metrics_collector=metrics)

   # Get metrics
   tool_metrics = metrics.get_metrics("Calculator")
   print(f"Success rate: {tool_metrics['success_rate']}")
   print(f"Error count: {tool_metrics['error_count']}")

Error Handling
--------------

Tool Error Recovery
~~~~~~~~~~~~~~~~~~~

Handle tool failures gracefully:

.. code-block:: python

   from massgen.tools import ToolWithFallback

   tool = ToolWithFallback(
       primary=PrimaryAPITool(),
       fallback=BackupAPITool(),
       retry_primary=3,
       fallback_on_errors=[500, 503]
   )

Tool Timeout Handling
~~~~~~~~~~~~~~~~~~~~~

Manage tool timeouts:

.. code-block:: python

   from massgen.tools import TimeoutHandler

   tool = WebSearch(
       timeout=10,
       timeout_handler=TimeoutHandler(
           action="retry",  # or "fail", "fallback"
           max_retries=2,
           backoff_factor=2.0
       )
   )

Best Practices
--------------

1. **Tool Selection**: Choose tools that match agent roles
2. **Error Handling**: Always implement proper error handling
3. **Input Validation**: Validate inputs before execution
4. **Resource Management**: Monitor and limit resource usage
5. **Caching**: Cache expensive tool results when appropriate
6. **Documentation**: Provide clear descriptions for custom tools
7. **Testing**: Test tools independently before agent integration

Next Steps
----------

* :doc:`mcp_integration` - Model Context Protocol integration
* :doc:`advanced_usage` - Advanced tool patterns
* :doc:`../examples/basic_examples` - Tool usage examples