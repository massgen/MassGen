General Framework Interoperability
===================================

**NEW in v0.1.6**

MassGen provides comprehensive interoperability with external agent frameworks through its custom tool system. This enables you to leverage specialized multi-agent frameworks as powerful tools within MassGen's coordination ecosystem.

Overview
--------

MassGen supports comprehensive interoperability with external agent frameworks through its custom tool system. External frameworks are wrapped as custom tools that MassGen agents can call

This chapter focuses on the **Custom Tool Integration** approach, which allows you to:

* Wrap entire multi-agent frameworks as single tools
* Maintain framework-specific orchestration patterns
* Combine multiple frameworks in hybrid agent teams
* Preserve each framework's unique capabilities

What is Framework Interoperability?
------------------------------------

Framework interoperability means using specialized agent frameworks like AgentScope, LangGraph, or OpenAI's Chat Completions API as tools within MassGen. Each framework becomes a powerful capability that MassGen agents can invoke.

**Key Benefits:**

* **Leverage Framework Strengths**: Use the best framework for each task
* **Preserve Framework Patterns**: Maintain sequential pipelines, state graphs, or nested chats
* **Hybrid Coordination**: Combine framework-specific patterns with MassGen's multi-agent coordination
* **Gradual Adoption**: Integrate existing framework implementations without rewriting

Architecture
------------

Custom Tool Wrapper Pattern
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each framework integration follows this pattern:

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

Supported Frameworks
--------------------

AgentScope Integration
~~~~~~~~~~~~~~~~~~~~~~

`AgentScope <https://github.com/modelscope/agentscope>`_ is a multi-agent framework that provides flexible agent orchestration patterns.

**Key Features:**

* Sequential agent pipelines
* Memory and message passing
* Multiple LLM backend support

**Example: Lesson Planner with AgentScope**

.. code-block:: yaml

   agents:
     - id: "agentscope_assistant"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["agentscope_lesson_planner"]
             category: "education"
             path: "massgen/tool/_extraframework_agents/agentscope_lesson_planner_tool.py"
             function: ["agentscope_lesson_planner"]
       system_message: |
         You have access to an AgentScope-powered lesson planning tool.
         Use it to create comprehensive fourth-grade lesson plans.

**Usage:**

.. code-block:: bash

   massgen --config path/to/config.yaml \
     "Create a lesson plan for photosynthesis"

**How It Works:**

The tool orchestrates four specialized AgentScope agents in sequence:

1. **Curriculum Standards Expert**: Identifies grade-level standards
2. **Lesson Planning Specialist**: Creates detailed lesson structure
3. **Lesson Plan Reviewer**: Reviews for age-appropriateness and effectiveness
4. **Lesson Plan Formatter**: Formats the final output

Each agent uses AgentScope's ``SimpleDialogAgent`` with OpenAI models, maintaining conversation history through AgentScope's memory system.

LangGraph Integration
~~~~~~~~~~~~~~~~~~~~~

`LangGraph <https://github.com/langchain-ai/langgraph>`_ provides state graph-based orchestration for complex agent workflows.

**Key Features:**

* State graph architecture
* Conditional routing and branching
* Integration with LangChain ecosystem
* Persistent state management

**Example: Lesson Planner with LangGraph**

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

**State Graph Architecture:**

.. code-block:: text

   curriculum_node -> planner_node -> reviewer_node -> formatter_node -> END

The workflow maintains state throughout execution:

* ``user_prompt``: Original request
* ``standards``: Curriculum standards from first node
* ``lesson_plan``: Draft plan from second node
* ``reviewed_plan``: Reviewed plan from third node
* ``final_plan``: Formatted output from final node

AG2 Custom Tool Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

While AG2 can be used as a backend (see :doc:`ag2_integration`), it can also be wrapped as a custom tool to leverage specific AG2 patterns like nested chats and group chats.

**Example: Nested Chat Lesson Planner**

.. code-block:: yaml

   agents:
     - id: "ag2_tool_user"
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

**Nested Chat Architecture:**

The tool uses AG2's nested chat pattern:

1. **Inner Chat 1**: Curriculum agent determines standards (2 turns)
2. **Group Chat**: Collaborative lesson planning with multiple agents
3. **Inner Chat 2**: Formatter agent creates final output

This demonstrates AG2's powerful orchestration patterns within MassGen.

OpenAI Chat Completions Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Direct integration with OpenAI's Chat Completions API as a multi-agent system.

**Key Features:**

* Native streaming support
* Multiple specialized "agents" via system prompts
* Sequential processing pipeline
* Full control over temperature and parameters

**Example Configuration:**

.. code-block:: yaml

   agents:
     - id: "openai_assistant"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["openai_assistant_lesson_planner"]
             category: "education"
             path: "massgen/tool/_extraframework_agents/openai_assistant_lesson_planner_tool.py"
             function: ["openai_assistant_lesson_planner"]
       system_message: |
         You have access to an OpenAI-powered multi-agent lesson planning tool
         with streaming support.

**Sequential Agent Pattern:**

Each "agent" is implemented as a separate API call with specialized system prompt:

1. **Curriculum Agent**: Role-specific prompt for standards
2. **Lesson Planner Agent**: Role-specific prompt for lesson design
3. **Reviewer Agent**: Role-specific prompt for quality review
4. **Formatter Agent**: Role-specific prompt for output formatting

Hybrid Multi-Framework Setup
-----------------------------

Combine Multiple Frameworks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can use multiple framework integrations in a single MassGen configuration:

.. code-block:: yaml

   agents:
     # Agent with AgentScope tool
     - id: "agentscope_specialist"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["agentscope_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/agentscope_lesson_planner_tool.py"
             function: ["agentscope_lesson_planner"]
       system_message: "You specialize in sequential agent pipelines using AgentScope."

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

* AgentScope specialist uses sequential pipelines
* LangGraph specialist uses state graphs
* Researcher provides web-based context
* All three collaborate through MassGen's coordination

Framework + Backend Hybrid
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine custom tool frameworks with backend frameworks:

.. code-block:: yaml

   agents:
     # AG2 backend agent (direct participation)
     - id: "ag2_coder"
       backend:
         type: ag2
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

     # Agent with LangGraph custom tool
     - id: "langgraph_planner"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["langgraph_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/langgraph_lesson_planner_tool.py"
             function: ["langgraph_lesson_planner"]
       system_message: "You create structured lesson plans using LangGraph."

     # Native Claude agent with MCP tools
     - id: "claude_analyst"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         mcp_servers:
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-weather"]

**This combines:**

* **AG2 backend**: Code execution and native AG2 orchestration
* **LangGraph tool**: State-based lesson planning
* **Claude with MCP**: Additional data access and analysis
* **MassGen coordination**: All three collaborate with voting

Creating Custom Framework Integrations
---------------------------------------

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
--------------

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

Use Cases
---------

Educational Content Creation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use framework-specific multi-agent patterns for lesson planning:

.. code-block:: bash

   massgen --config agentscope_lesson_planner.yaml \
     "Create a comprehensive lesson plan for teaching photosynthesis to fourth graders"

**Why framework integration?**

* AgentScope's sequential pipeline ensures proper flow
* Multiple specialized agents provide comprehensive coverage
* Framework handles agent coordination internally

Framework Comparison
~~~~~~~~~~~~~~~~~~~~

Run multiple frameworks on the same task to compare approaches:

.. code-block:: yaml

   agents:
     - id: "agentscope_approach"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["agentscope_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/agentscope_lesson_planner_tool.py"
             function: ["agentscope_lesson_planner"]

     - id: "langgraph_approach"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["langgraph_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/langgraph_lesson_planner_tool.py"
             function: ["langgraph_lesson_planner"]

     - id: "ag2_approach"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["ag2_lesson_planner"]
             path: "massgen/tool/_extraframework_agents/ag2_lesson_planner_tool.py"
             function: ["ag2_lesson_planner"]

Each agent uses a different framework, and MassGen's coordination helps identify the best approach.

Installation
------------

Framework-Specific Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Install frameworks as needed:

**AgentScope:**

.. code-block:: bash

   pip install agentscope

**LangGraph:**

.. code-block:: bash

   pip install langgraph langchain-openai

**AG2:**

.. code-block:: bash

   uv pip install -e ".[external]"

**All frameworks:**

.. code-block:: bash

   pip install agentscope langgraph langchain-openai
   uv pip install -e ".[external]"

Troubleshooting
---------------

Framework Not Found
~~~~~~~~~~~~~~~~~~~

**Error:** ``ModuleNotFoundError: No module named 'agentscope'``

**Solution:**

.. code-block:: bash

   pip install agentscope  # or the appropriate framework

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

Next Steps
----------

* :doc:`ag2_integration` - AG2 backend integration approach
* :doc:`custom_tools` - General custom tool development
* :doc:`mcp_integration` - Model Context Protocol tools
* :doc:`tools` - Complete tool system overview
* :doc:`../examples/advanced_patterns` - Advanced integration patterns

Examples Repository
-------------------

Find complete working examples in the repository:

* ``massgen/tool/_extraframework_agents/`` - Framework integration implementations
* ``massgen/configs/tools/custom_tools/`` - Example configurations
* ``examples/`` - Complete usage examples

Community Frameworks
--------------------

Want to integrate another framework? We welcome contributions!

**Popular frameworks to consider:**

* CrewAI
* Haystack
* Semantic Kernel
* AutoGPT

See :doc:`../development/contributing` for contribution guidelines.
