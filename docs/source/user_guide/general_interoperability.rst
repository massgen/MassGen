General Framework Interoperability
===================================

**NEW in v0.1.6**

MassGen provides comprehensive interoperability with external agent frameworks through its custom tool system. This enables you to leverage specialized multi-agent frameworks as powerful tools within MassGen's coordination ecosystem.

Quick Start
-----------

Try Framework Integrations
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**AG2 (AutoGen) - Nested Chat Patterns:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/ag2_lesson_planner_example.yaml \
     "Create a lesson plan for teaching fractions to fourth graders"

**LangGraph - State Graph Workflows:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/langgraph_lesson_planner_example.yaml \
     "Design a lesson plan for the water cycle"

**AgentScope - Sequential Pipelines:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/agentscope_lesson_planner_example.yaml \
     "Create a lesson plan for photosynthesis"

**OpenAI Chat Completions - Multi-Agent API:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/openai_assistant_lesson_planner_example.yaml \
     "Develop a lesson plan for ecosystems"

**SmolAgent - Tool-Using Agents:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/smolagent_lesson_planner_example.yaml \
     "Build a lesson plan for fractions"

**Compare Multiple Frameworks:**

.. code-block:: bash

   massgen \
     --config @examples/tools/custom_tools/interop/ag2_and_langgraph_lesson_planner.yaml \
     "Create a lesson plan comparing different approaches"

These examples demonstrate how each framework can be used as a tool within MassGen agents, leveraging their unique orchestration patterns while participating in MassGen's multi-agent coordination.

Installation
------------

Install the required framework dependencies:

**For AG2:**

.. code-block:: bash

   uv pip install -e ".[external]"

**For LangGraph:**

.. code-block:: bash

   pip install langgraph langchain-openai

**For AgentScope:**

.. code-block:: bash

   pip install agentscope

**For SmolAgent:**

.. code-block:: bash

   pip install smolagents

**OpenAI Chat Completions:**

No additional installation needed - uses standard OpenAI SDK already included with MassGen.

**For all frameworks:**

.. code-block:: bash

   pip install agentscope langgraph langchain-openai smolagents
   uv pip install -e ".[external]"

What is Framework Interoperability?
------------------------------------

Framework interoperability means using specialized agent frameworks as tools within MassGen. Each framework becomes a powerful capability that MassGen agents can invoke.

**Supported Frameworks:**

* **AG2 (AutoGen)** - Nested chats and group collaboration
* **LangGraph** - State graph-based workflows
* **AgentScope** - Sequential agent pipelines
* **OpenAI Chat Completions** - Multi-agent API patterns
* **SmolAgent** - Tool-using agent framework from HuggingFace

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
* **Streaming support** for real-time output

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

   massgen --config @examples/tools/custom_tools/interop/ag2_lesson_planner_example.yaml \
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

**Note:** Streaming support coming in future release.

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

   massgen --config @examples/tools/custom_tools/interop/langgraph_lesson_planner_example.yaml \
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

AgentScope Integration
~~~~~~~~~~~~~~~~~~~~~~

`AgentScope <https://github.com/modelscope/agentscope>`_ is a multi-agent framework providing flexible agent orchestration patterns.

**Key Features:**

* Sequential agent pipelines
* Memory and message passing
* Multiple LLM backend support
* Flexible conversation management

**Note:** Streaming support coming in future release.

**Basic Configuration:**

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

   massgen --config @examples/tools/custom_tools/interop/agentscope_lesson_planner_example.yaml \
     "Create a lesson plan for photosynthesis"

**How AgentScope Integration Works:**

The tool orchestrates four specialized AgentScope agents in sequence:

1. **Curriculum Standards Expert**: Identifies grade-level standards
2. **Lesson Planning Specialist**: Creates detailed lesson structure
3. **Lesson Plan Reviewer**: Reviews for age-appropriateness
4. **Lesson Plan Formatter**: Formats the final output

Each agent uses AgentScope's ``SimpleDialogAgent`` with OpenAI models, maintaining conversation history through AgentScope's memory system.

OpenAI Chat Completions Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Direct integration with OpenAI's Chat Completions API as a multi-agent system.

**Key Features:**

* **Native streaming support** for real-time output
* Multiple specialized "agents" via system prompts
* Sequential processing pipeline
* Full control over temperature and parameters

**Basic Configuration:**

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

**Usage:**

.. code-block:: bash

   massgen --config @examples/tools/custom_tools/interop/openai_assistant_lesson_planner_example.yaml \
     "Develop a lesson plan for ecosystems"

**How OpenAI Integration Works:**

Each "agent" is implemented as a separate API call with specialized system prompt:

1. **Curriculum Agent**: Role-specific prompt for standards
2. **Lesson Planner Agent**: Role-specific prompt for lesson design
3. **Reviewer Agent**: Role-specific prompt for quality review
4. **Formatter Agent**: Role-specific prompt for output formatting

SmolAgent Integration
~~~~~~~~~~~~~~~~~~~~~

`SmolAgent <https://github.com/huggingface/smolagents>`_ is HuggingFace's lightweight tool-using agent framework.

**Key Features:**

* Tool-using agents with code execution
* CodeAgent for autonomous tool management
* Integration with HuggingFace models
* Lightweight and efficient

**Note:** Streaming support coming in future release.

**Basic Configuration:**

.. code-block:: yaml

   agents:
     - id: "smolagent_assistant"
       backend:
         type: "openai"
         model: "gpt-4o"
         custom_tools:
           - name: ["smolagent_lesson_planner"]
             category: "education"
             path: "massgen/tool/_extraframework_agents/smolagent_lesson_planner_tool.py"
             function: ["smolagent_lesson_planner"]
       system_message: |
         You have access to a SmolAgent-powered lesson planning tool
         that uses tool-calling agents.

**Usage:**

.. code-block:: bash

   massgen --config @examples/tools/custom_tools/interop/smolagent_lesson_planner_example.yaml \
     "Build a lesson plan for fractions"

**How SmolAgent Integration Works:**

The tool uses SmolAgent's ``CodeAgent`` with custom tools:

1. **Tool Definition**: Custom tools for each planning stage
2. **Agent Orchestration**: CodeAgent manages tool execution
3. **Sequential Processing**: Tools called in order by the agent
4. **Result Aggregation**: Final lesson plan assembled from tool outputs

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

   For long-running operations, yield intermediate results (currently supported for AG2 and OpenAI Chat Completions):

   .. code-block:: python

      yield ExecutionResult(
          output_blocks=[TextContent(data="Step 1 complete\n")],
          is_log=True,  # Mark as log output
      )

   **Note:** Streaming support is currently available for AG2 and OpenAI Chat Completions. Other frameworks will receive streaming support in future releases.

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

Future Framework Support
-------------------------

MassGen v0.1.6 includes full support for five agent frameworks:

* **AG2 (AutoGen)** - Nested chats and group collaboration
* **LangGraph** - State graph-based workflows
* **AgentScope** - Sequential agent pipelines
* **OpenAI Chat Completions** - Multi-agent API patterns
* **SmolAgent** - Tool-using agents from HuggingFace

All frameworks follow the same custom tool integration pattern. See the examples in ``massgen/tool/_extraframework_agents/`` for implementation details.

**Want to integrate another framework?** We welcome contributions for additional frameworks:

* CrewAI
* Haystack
* Semantic Kernel
* AutoGPT

See :doc:`../development/contributing` for contribution guidelines.

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
