Tool System API
===============

API documentation for MassGen's custom tool system. This section is for developers who need programmatic access to the tool system.

.. note::

   **For Users:** See :doc:`../user_guide/custom_tools` for how to create and use custom tools with YAML configuration.

   **For Developers:** This section documents the internal APIs for programmatic tool management.

Core Classes
------------

ToolManager
~~~~~~~~~~~

.. autoclass:: massgen.tool.ToolManager
   :members:
   :undoc-members:
   :show-inheritance:

The ``ToolManager`` class provides programmatic control over tool registration, categorization, and execution.

**Key Methods:**

* ``add_tool_function()`` - Register a tool
* ``delete_tool_function()`` - Remove a tool
* ``setup_category()`` - Create a tool category
* ``modify_categories()`` - Enable/disable categories
* ``fetch_tool_schemas()`` - Get JSON schemas for active tools
* ``execute_tool()`` - Execute a tool and stream results

ExecutionResult
~~~~~~~~~~~~~~~

.. autoclass:: massgen.tool.ExecutionResult
   :members:
   :undoc-members:
   :show-inheritance:

Container for tool execution outputs. Tools must return this type.

**Fields:**

* ``output_blocks`` - List of content blocks (TextContent, ImageContent, AudioContent)
* ``meta_info`` - Optional metadata dictionary
* ``is_streaming`` - Whether this is a streaming result
* ``is_final`` - Whether this is the final result in a stream
* ``was_interrupted`` - Whether execution was interrupted

Content Types
~~~~~~~~~~~~~

.. autoclass:: massgen.tool.TextContent
   :members:
   :undoc-members:
   :show-inheritance:

Text content block for plain text output.

.. autoclass:: massgen.tool.ImageContent
   :members:
   :undoc-members:
   :show-inheritance:

Image content block for base64-encoded image data.

.. autoclass:: massgen.tool.AudioContent
   :members:
   :undoc-members:
   :show-inheritance:

Audio content block for base64-encoded audio data.

RegisteredToolEntry
~~~~~~~~~~~~~~~~~~~

.. autoclass:: massgen.tool.RegisteredToolEntry
   :members:
   :undoc-members:
   :show-inheritance:

Internal data model for registered tools.

Exceptions
----------

.. autoclass:: massgen.tool.ToolException
   :members:
   :undoc-members:
   :show-inheritance:

Base exception for tool-related errors.

.. autoclass:: massgen.tool.ToolNotFoundException
   :members:
   :undoc-members:
   :show-inheritance:

Raised when a tool is not found.

.. autoclass:: massgen.tool.InvalidToolArgumentsException
   :members:
   :undoc-members:
   :show-inheritance:

Raised when tool arguments are invalid.

.. autoclass:: massgen.tool.ToolExecutionException
   :members:
   :undoc-members:
   :show-inheritance:

Raised when tool execution fails.

.. autoclass:: massgen.tool.CategoryNotFoundException
   :members:
   :undoc-members:
   :show-inheritance:

Raised when a category is not found.

Built-in Tools
--------------

Code Execution
~~~~~~~~~~~~~~

.. autofunction:: massgen.tool.run_python_script

Execute Python code in an isolated subprocess.

.. autofunction:: massgen.tool.run_shell_script

Execute shell commands in a subprocess.

File Operations
~~~~~~~~~~~~~~~

.. autofunction:: massgen.tool.read_file_content

Read file content with optional line range.

.. autofunction:: massgen.tool.save_file_content

Write content to a file.

.. autofunction:: massgen.tool.append_file_content

Append or insert content into a file.

Workflow Toolkits
-----------------

NewAnswerToolkit
~~~~~~~~~~~~~~~~

.. autoclass:: massgen.tool.workflow_toolkits.NewAnswerToolkit
   :members:
   :undoc-members:
   :show-inheritance:

Toolkit for agents to submit new answers during coordination.

VoteToolkit
~~~~~~~~~~~

.. autoclass:: massgen.tool.workflow_toolkits.VoteToolkit
   :members:
   :undoc-members:
   :show-inheritance:

Toolkit for agents to vote for other agents' answers.

Formatters
----------

Tool formatters convert custom tools to backend-specific formats.

.. autoclass:: massgen.formatter._claude_formatter.ClaudeToolFormatter
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: massgen.formatter._gemini_formatter.GeminiToolFormatter
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: massgen.formatter._chat_completions_formatter.ChatCompletionsToolFormatter
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: massgen.formatter._response_formatter.ResponseToolFormatter
   :members:
   :undoc-members:
   :show-inheritance:

Usage Examples
--------------

Programmatic Tool Registration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from massgen.tool import ToolManager, ExecutionResult, TextContent

   # Create manager
   manager = ToolManager()

   # Define a tool
   async def my_tool(param: str) -> ExecutionResult:
       """My custom tool."""
       return ExecutionResult(
           output_blocks=[TextContent(data=f"Processed: {param}")]
       )

   # Register it
   manager.add_tool_function(func=my_tool, category="custom")

   # Get schemas
   schemas = manager.fetch_tool_schemas()

   # Execute
   async for result in manager.execute_tool({
       "name": "custom_tool__my_tool",
       "input": {"param": "test"}
   }):
       print(result.output_blocks[0].data)

Category Management
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create category
   manager.setup_category(
       category_name="data_science",
       description="Data analysis tools",
       enabled=True
   )

   # Register tools in category
   manager.add_tool_function(
       func=analyze_data,
       category="data_science"
   )

   # Enable/disable categories
   manager.modify_categories(["data_science"], enabled=False)

   # Delete categories
   manager.delete_categories("old_category")

Streaming Tool Results
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from typing import AsyncGenerator
   import asyncio

   async def streaming_tool() -> AsyncGenerator[ExecutionResult, None]:
       """Tool that streams progress updates."""

       # Initial status
       yield ExecutionResult(
           output_blocks=[TextContent(data="Starting...")],
           is_streaming=True,
           is_final=False
       )

       # Progress updates
       for i in range(5):
           await asyncio.sleep(1)
           yield ExecutionResult(
               output_blocks=[TextContent(data=f"Progress: {(i+1)*20}%")],
               is_streaming=True,
               is_final=False
           )

       # Final result
       yield ExecutionResult(
           output_blocks=[TextContent(data="Complete!")],
           is_streaming=True,
           is_final=True
       )

See Also
--------

* :doc:`../user_guide/custom_tools` - User guide for creating custom tools
* :doc:`../user_guide/tools` - Tools and capabilities overview
* :doc:`backends` - Backend implementations that use tools
* :doc:`formatter` - Tool formatting utilities
