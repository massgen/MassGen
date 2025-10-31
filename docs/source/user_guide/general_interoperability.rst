General Framework Interoperability
===================================

**NEW in v0.1.6**

MassGen provides interoperability with external agent frameworks through its custom tool system. This enables you to leverage specialized multi-agent frameworks like AG2 and LangGraph as powerful tools within MassGen's coordination ecosystem.

Quick Start
-----------

Try Framework Integrations
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**AG2 Lesson Planner:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/ag2_lesson_planner_example.yaml \
     "Create a lesson plan for teaching fractions to fourth graders"

**LangGraph Lesson Planner:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/langgraph_lesson_planner_example.yaml \
     "Design a lesson plan for the water cycle"

**Compare Both Approaches:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/ag2_and_langgraph_lesson_planner.yaml \
     "Create a lesson plan for photosynthesis"

These examples demonstrate how AG2 and LangGraph can be used as tools within MassGen agents, each leveraging their unique orchestration patterns while participating in MassGen's multi-agent coordination.

Installation
------------

Install the required framework dependencies:

**For AG2:**

.. code-block:: bash

   uv pip install -e ".[external]"

**For LangGraph:**

.. code-block:: bash

   pip install langgraph langchain-openai

**For both:**

.. code-block:: bash

   pip install langgraph langchain-openai
   uv pip install -e ".[external]"

What is Framework Interoperability?
------------------------------------

Framework interoperability means using specialized agent frameworks like AG2 and LangGraph as tools within MassGen. Each framework becomes a powerful capability that MassGen agents can invoke.

**Key Benefits:**

* **Leverage Framework Strengths**: Use the best framework for each task
* **Preserve Framework Patterns**: Maintain nested chats (AG2) or state graphs (LangGraph)
* **Hybrid Coordination**: Combine framework-specific patterns with MassGen's multi-agent coordination
* **Gradual Adoption**: Integrate existing framework implementations without rewriting

**How It Works:**

External frameworks are wrapped as custom tools that MassGen agents can call. This allows you to:

* Wrap entire multi-agent frameworks as single tools
* Maintain framework-specific orchestration patterns
* Combine multiple frameworks in hybrid agent teams
* Preserve each framework's unique capabilities

Supported Frameworks
--------------------

AG2 Integration
~~~~~~~~~~~~~~~

`AG2 <https://github.com/ag2ai/ag2>`_ (formerly AutoGen) is a multi-agent framework that provides powerful orchestration patterns like nested chats and group chats.

**Key Features:**

* Nested chat patterns for complex workflows
* Group chat collaboration between multiple agents
* Code execution capabilities
* Rich agent conversation management

**Basic Configuration:**

.. code-block:: yaml

   agents:
     - id: "ag2_assistant"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["ag2_lesson_planner"]
             category: "education"
             path: "massgen/tool/_extraframework_agents/ag2_lesson_planner_tool.py"
             function: ["ag2_lesson_planner"]
       system_message: |
         You have access to an AG2-powered lesson planning tool that uses
         nested chats and group collaboration.

**Usage:**

.. code-block:: bash

   massgen --config path/to/config.yaml \
     "Create a lesson plan for fractions"

**How AG2 Integration Works:**

The AG2 tool uses nested chat patterns:

1. **Inner Chat 1**: Curriculum agent determines standards (2 turns)
2. **Group Chat**: Collaborative lesson planning with multiple agents
3. **Inner Chat 2**: Formatter agent creates final output

This demonstrates AG2's powerful orchestration patterns within MassGen's coordination system.

LangGraph Integration
~~~~~~~~~~~~~~~~~~~~~

`LangGraph <https://github.com/langchain-ai/langgraph>`_ provides state graph-based orchestration for complex agent workflows.

**Key Features:**

* State graph architecture
* Conditional routing and branching
* Integration with LangChain ecosystem
* Persistent state management

**Basic Configuration:**

.. code-block:: yaml

   agents:
     - id: "langgraph_assistant"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["langgraph_lesson_planner"]
             category: "education"
             path: "massgen/tool/_extraframework_agents/langgraph_lesson_planner_tool.py"
             function: ["langgraph_lesson_planner"]
       system_message: |
         You have access to a LangGraph-powered lesson planning tool.
         Use it for creating structured lesson plans with state-based workflows.

**Usage:**

.. code-block:: bash

   massgen --config path/to/config.yaml \
     "Design a lesson plan for the water cycle"

**How LangGraph Integration Works:**

The workflow uses a state graph architecture:

.. code-block:: text

   curriculum_node -> planner_node -> reviewer_node -> formatter_node -> END

The graph maintains state throughout execution:

* ``user_prompt``: Original request
* ``standards``: Curriculum standards from first node
* ``lesson_plan``: Draft plan from second node
* ``reviewed_plan``: Reviewed plan from third node
* ``final_plan``: Formatted output from final node

Hybrid Multi-Framework Setups
------------------------------

Combine Multiple Frameworks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can use multiple framework integrations in a single MassGen configuration:

.. code-block:: yaml

   agents:
     # Agent with AG2 tool
     - id: "ag2_specialist"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["ag2_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/ag2_lesson_planner_tool.py"
             function: ["ag2_lesson_planner"]
       system_message: "You specialize in nested chat workflows using AG2."

     # Agent with LangGraph tool
     - id: "langgraph_specialist"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["langgraph_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/langgraph_lesson_planner_tool.py"
             function: ["langgraph_lesson_planner"]
       system_message: "You specialize in state-based workflows using LangGraph."

     # Native MassGen agent with web search
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
       system_message: "You research educational standards and best practices."

**This setup enables:**

* AG2 specialist uses nested chat patterns
* LangGraph specialist uses state graphs
* Researcher provides web-based context
* All three collaborate through MassGen's coordination

Use Cases
---------

Educational Content Creation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use framework-specific multi-agent patterns for lesson planning:

.. code-block:: bash

   massgen --config ag2_lesson_planner.yaml \
     "Create a comprehensive lesson plan for teaching photosynthesis to fourth graders"

**Why framework integration?**

* AG2's nested chats ensure proper workflow orchestration
* LangGraph's state graphs maintain context across planning stages
* Multiple specialized agents provide comprehensive coverage
* Frameworks handle internal coordination while MassGen coordinates overall strategy

Framework Comparison
~~~~~~~~~~~~~~~~~~~~

Run multiple frameworks on the same task to compare approaches:

.. code-block:: yaml

   agents:
     - id: "ag2_approach"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["ag2_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/ag2_lesson_planner_tool.py"
             function: ["ag2_lesson_planner"]

     - id: "langgraph_approach"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["langgraph_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/langgraph_lesson_planner_tool.py"
             function: ["langgraph_lesson_planner"]

Each agent uses a different framework, and MassGen's coordination helps identify the best approach.

Creating Custom Framework Integrations
---------------------------------------

Want to integrate a new framework or customize existing ones? This section shows you how.

Architecture Overview
~~~~~~~~~~~~~~~~~~~~~

Each framework integration follows a clean separation pattern:

.. code-block:: python

   # 1. Core framework logic (pure framework implementation)
   async def run_framework_agent(messages, api_key):
       # Pure framework code here
       # Returns: result string
       pass

   # 2. MassGen custom tool wrapper
   @context_params("prompt")
   async def framework_tool(prompt):
       # Environment setup
       # Call core framework function
       # Wrap result in ExecutionResult
       yield ExecutionResult(...)

**This separation ensures:**

* Framework code remains portable and testable
* MassGen integration is clean and minimal
* Easy debugging and maintenance

Wrapper Template
~~~~~~~~~~~~~~~~

To integrate a new framework, follow this template:

.. code-block:: python

   # your_framework_tool.py
   import os
   from typing import Any, AsyncGenerator, Dict, List

   # Import your framework
   from your_framework import YourFrameworkAgent

   from massgen.tool import context_params
   from massgen.tool._result import ExecutionResult, TextContent


   async def run_your_framework_agent(
       messages: List[Dict[str, Any]],
       api_key: str,
   ) -> str:
       """
       Core framework logic - pure framework implementation.

       Args:
           messages: Complete message history from orchestrator
           api_key: API key for LLM

       Returns:
           Result as string
       """
       # 1. Extract user request from messages
       user_prompt = ""
       for msg in messages:
           if isinstance(msg, dict) and msg.get("role") == "user":
               user_prompt = msg.get("content", "")
               break

       # 2. Initialize your framework
       agent = YourFrameworkAgent(api_key=api_key)

       # 3. Run framework-specific logic
       result = await agent.run(user_prompt)

       # 4. Return result as string
       return result


   @context_params("prompt")
   async def your_framework_tool(
       prompt: List[Dict[str, Any]],
   ) -> AsyncGenerator[ExecutionResult, None]:
       """
       MassGen custom tool wrapper.

       Args:
           prompt: Processed message list from orchestrator

       Yields:
           ExecutionResult containing the result or error messages
       """
       # Get API key from environment
       api_key = os.getenv("YOUR_FRAMEWORK_API_KEY")

       if not api_key:
           yield ExecutionResult(
               output_blocks=[
                   TextContent(data="Error: API key not found"),
               ],
           )
           return

       try:
           # Call core framework function
           result = await run_your_framework_agent(
               messages=prompt,
               api_key=api_key,
           )

           # Yield result
           yield ExecutionResult(
               output_blocks=[
                   TextContent(data=f"Your Framework Result:\n\n{result}"),
               ],
           )

       except Exception as e:
           yield ExecutionResult(
               output_blocks=[
                   TextContent(data=f"Error: {str(e)}"),
               ],
           )

Configuration Template
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "your_framework_agent"
       backend:
         type: "openai"  # or any backend
         model: "gpt-4o"
         custom_tools:
           - name: ["your_framework_tool"]
             category: "custom"
             path: "path/to/your_framework_tool.py"
             function: ["your_framework_tool"]
       system_message: |
         You have access to a custom framework tool.
         Use it when appropriate for specialized tasks.

Best Practices
~~~~~~~~~~~~~~

1. **Separation of Concerns**

   Keep framework logic separate from MassGen integration:

   * Core function: Pure framework implementation
   * Wrapper function: MassGen integration only

   This makes testing and maintenance easier.

2. **Error Handling**

   Always wrap framework calls in try-except:

   .. code-block:: python

      try:
          result = await run_framework_agent(...)
          yield ExecutionResult(output_blocks=[TextContent(data=result)])
      except Exception as e:
          yield ExecutionResult(
              output_blocks=[TextContent(data=f"Error: {str(e)}")]
          )

3. **Environment Configuration**

   Use environment variables for API keys and sensitive data:

   .. code-block:: python

      api_key = os.getenv("FRAMEWORK_API_KEY")
      if not api_key:
          yield ExecutionResult(
              output_blocks=[TextContent(data="Error: API key not found")]
          )
          return

4. **Streaming Support**

   For long-running operations, yield intermediate results:

   .. code-block:: python

      yield ExecutionResult(
          output_blocks=[TextContent(data="Step 1 complete\n")],
          is_log=True,  # Mark as log output
      )

5. **Message Extraction**

   Properly extract user requests from message history:

   .. code-block:: python

      user_prompt = ""
      for msg in messages:
          if isinstance(msg, dict) and msg.get("role") == "user":
              user_prompt = msg.get("content", "")
              break

Troubleshooting
---------------

Framework Not Found
~~~~~~~~~~~~~~~~~~~

**Error:** ``ModuleNotFoundError: No module named 'ag2'`` or ``No module named 'langgraph'``

**Solution:**

.. code-block:: bash

   # For AG2
   uv pip install -e ".[external]"

   # For LangGraph
   pip install langgraph langchain-openai

API Key Issues
~~~~~~~~~~~~~~

**Error:** ``Error: OPENAI_API_KEY not found``

**Solution:**

Set the required environment variable:

.. code-block:: bash

   export OPENAI_API_KEY="your-key-here"

Tool Not Recognized
~~~~~~~~~~~~~~~~~~~

**Error:** Tool function not found

**Solution:**

* Verify ``path`` points to correct Python file
* Ensure ``function`` name matches the decorated function
* Check that file is in Python path or use absolute path

Async/Sync Mismatch
~~~~~~~~~~~~~~~~~~~

**Error:** ``coroutine was never awaited``

**Solution:**

Ensure your tool function is async and uses ``AsyncGenerator``:

.. code-block:: python

   @context_params("prompt")
   async def your_tool(prompt) -> AsyncGenerator[ExecutionResult, None]:
       # Use async/await throughout
       result = await framework_function()
       yield ExecutionResult(...)

Legacy AG2 Backend Approach (Not Recommended)
----------------------------------------------

**Note:** This section documents the older AG2 backend integration approach for backwards compatibility. We recommend using the **Custom Tool Integration** approach described above instead.

What Was the Backend Approach?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In earlier versions (v0.0.28), MassGen supported AG2 as a direct backend type, where AG2 agents participated directly in MassGen's coordination system:

.. code-block:: yaml

   agents:
     - id: "ag2_coder"
       backend:
         type: ag2                  # AG2 as a backend
         agent_config:
           type: assistant
           name: "AG2_Coder"
           system_message: "You write and execute Python code"
           llm_config:
             api_type: "openai"
             model: "gpt-4o"
           code_execution_config:
             executor:
               type: "LocalCommandLineCodeExecutor"

Why Not Use the Backend Approach?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitations:**

* AG2 agents participated directly in coordination, which could be inflexible
* Limited ability to combine AG2's internal multi-agent patterns with MassGen coordination
* Less control over when and how AG2 agents were invoked
* Difficult to preserve AG2-specific orchestration patterns (nested chats, group chats)

**The custom tool approach provides:**

* Better separation of concerns
* Ability to wrap complex AG2 multi-agent workflows as single tools
* More flexible hybrid architectures
* Preservation of AG2's unique orchestration capabilities

Backwards Compatibility
~~~~~~~~~~~~~~~~~~~~~~~~

The backend approach still works and is backwards compatible. If you have existing configurations using ``type: ag2`` in backend configuration, they will continue to function.

However, for new implementations, we recommend:

1. **Use AG2 as a custom tool** (see ``AG2 Integration`` section above)
2. **Wrap AG2 multi-agent patterns** as tools to preserve their orchestration
3. **Leverage hybrid architectures** with custom tool + backend combinations

Migration Example
~~~~~~~~~~~~~~~~~

To migrate from the old backend approach to the new custom tool approach:

**Step 1: Build your custom tool** (see `Creating Custom Framework Integrations`_ section for the template)

Create a Python file with your AG2 logic wrapped as a custom tool following the wrapper pattern.

**Step 2: Update your YAML configuration**

**Old approach (backend):**

.. code-block:: yaml

   agents:
     - id: "ag2_coder"
       backend:
         type: ag2
         agent_config:
           type: assistant
           # ...

**New approach (custom tool):**

.. code-block:: yaml

   agents:
     - id: "assistant_with_ag2_tool"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["ag2_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/ag2_lesson_planner_tool.py"
             function: ["ag2_lesson_planner"]
       system_message: |
         You have access to an AG2-powered tool that uses
         nested chats and group collaboration.

The new approach gives you more control and better integration with MassGen's coordination system.

Additional Framework Support
-----------------------------

Beyond AG2 and LangGraph, we also have experimental support for:

* **AgentScope** - Sequential agent pipelines with flexible orchestration
* **OpenAI Chat Completions** - Direct multi-agent patterns using OpenAI's API

These frameworks follow the same custom tool integration pattern. See the examples in ``massgen/tool/_extraframework_agents/`` for implementation details.

Want to integrate another framework? We welcome contributions! See :doc:`../development/contributing` for contribution guidelines.

Next Steps
----------

* :doc:`custom_tools` - General custom tool development
* :doc:`mcp_integration` - Model Context Protocol tools
* :doc:`tools` - Complete tool system overview
* :doc:`../examples/advanced_patterns` - Advanced integration patterns

Examples Repository
-------------------

Find complete working examples in the repository:

* ``massgen/tool/_extraframework_agents/`` - Framework integration implementations
* ``massgen/configs/tools/custom_tools/interop/`` - Example configurations
* Use ``@examples/tools/custom_tools/interop/`` prefix when running configs
