# -*- coding: utf-8 -*-
"""
LangGraph Lesson Planner Tool
This tool demonstrates interoperability by wrapping LangGraph's state graph functionality as a MassGen custom tool.
"""

import operator
import os
from typing import Annotated, Any, AsyncGenerator, Dict, List, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from massgen.tool import context_params
from massgen.tool._result import ExecutionResult, TextContent


class LessonPlannerState(TypedDict):
    """State for the lesson planner workflow."""

    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_prompt: str
    context: str
    standards: str
    lesson_plan: str
    reviewed_plan: str
    final_plan: str


async def run_langgraph_lesson_planner_agent(
    messages: List[Dict[str, Any]],
    api_key: str,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Core LangGraph lesson planner agent - pure LangGraph implementation.

    This function contains the pure LangGraph logic for creating lesson plans
    using a state graph architecture with multiple specialized nodes.

    Args:
        messages: Complete message history from orchestrator
        api_key: OpenAI API key for the agents

    Yields:
        Dict with 'type' ('log' or 'output') and 'content' (the message)

    Raises:
        Exception: Any errors during agent execution
    """
    if not messages:
        raise ValueError("No messages provided for lesson planning.")

    # Extract the user's topic/request from messages
    user_prompt = ""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            user_prompt = msg.get("content", "")
            break

    if not user_prompt:
        # Fallback: use the entire messages as string
        user_prompt = str(messages)
    # Initialize the language model
    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=api_key,
        temperature=0.7,
    )

    # Define the curriculum standards node
    async def curriculum_node(state: LessonPlannerState) -> LessonPlannerState:
        """Determine curriculum standards and learning objectives."""
        system_msg = SystemMessage(
            content="""You are a curriculum standards expert for fourth grade education.
        When given a topic, you provide relevant grade-level standards and learning objectives.
        Format every response as:
        STANDARDS:
        - [Standard 1]
        - [Standard 2]
        OBJECTIVES:
        - By the end of this lesson, students will be able to [objective 1]
        - By the end of this lesson, students will be able to [objective 2]""",
        )

        # Build context message if provided
        context_info = f"\n\nAdditional Context: {state['context']}" if state.get("context") else ""
        human_msg = HumanMessage(content=f"Please provide fourth grade standards and objectives for: {state['user_prompt']}{context_info}")

        messages_to_send = [system_msg, human_msg]
        response = await llm.ainvoke(messages_to_send)

        return {
            "messages": [response],
            "standards": response.content,
            "user_prompt": state["user_prompt"],
            "context": state["context"],
            "lesson_plan": "",
            "reviewed_plan": "",
            "final_plan": "",
        }

    # Define the lesson planner node
    async def lesson_planner_node(state: LessonPlannerState) -> LessonPlannerState:
        """Create a detailed lesson plan based on standards."""
        system_msg = SystemMessage(
            content="""You are a lesson planning specialist.
        Given standards and objectives, you create detailed lesson plans including:
        - Opening/Hook (5-10 minutes)
        - Main Activity (20-30 minutes)
        - Practice Activity (15-20 minutes)
        - Assessment/Closure (5-10 minutes)
        Format as a structured lesson plan with clear timing and materials needed.""",
        )

        human_msg = HumanMessage(content=f"Based on these standards and objectives, create a detailed lesson plan:\n\n{state['standards']}")

        messages_to_send = [system_msg, human_msg]
        response = await llm.ainvoke(messages_to_send)

        return {
            "messages": state["messages"] + [response],
            "lesson_plan": response.content,
            "user_prompt": state["user_prompt"],
            "context": state["context"],
            "standards": state["standards"],
            "reviewed_plan": "",
            "final_plan": "",
        }

    # Define the lesson reviewer node
    async def lesson_reviewer_node(state: LessonPlannerState) -> LessonPlannerState:
        """Review and provide feedback on the lesson plan."""
        system_msg = SystemMessage(
            content="""You are a lesson plan reviewer who ensures:
        1. Age-appropriate content and activities
        2. Alignment with provided standards
        3. Realistic timing
        4. Clear instructions
        5. Differentiation opportunities
        Provide specific feedback in these areas and suggest improvements if needed.
        Then provide an improved version of the lesson plan incorporating your feedback.""",
        )

        human_msg = HumanMessage(content=f"Please review this lesson plan:\n\n{state['lesson_plan']}")

        messages_to_send = [system_msg, human_msg]
        response = await llm.ainvoke(messages_to_send)

        return {
            "messages": state["messages"] + [response],
            "reviewed_plan": response.content,
            "user_prompt": state["user_prompt"],
            "context": state["context"],
            "standards": state["standards"],
            "lesson_plan": state["lesson_plan"],
            "final_plan": "",
        }

    # Define the formatter node
    async def formatter_node(state: LessonPlannerState) -> LessonPlannerState:
        """Format the final lesson plan to a standard format."""
        system_msg = SystemMessage(
            content="""You are a lesson plan formatter. Format the complete plan as follows:
<title>Lesson plan title</title>
<standards>Standards covered</standards>
<learning_objectives>Key learning objectives</learning_objectives>
<materials>Materials required</materials>
<activities>Lesson plan activities</activities>
<assessment>Assessment details</assessment>""",
        )

        human_msg = HumanMessage(content=f"Format this reviewed lesson plan:\n\n{state['reviewed_plan']}")

        messages_to_send = [system_msg, human_msg]
        response = await llm.ainvoke(messages_to_send)

        return {
            "messages": state["messages"] + [response],
            "final_plan": response.content,
            "user_prompt": state["user_prompt"],
            "context": state["context"],
            "standards": state["standards"],
            "lesson_plan": state["lesson_plan"],
            "reviewed_plan": state["reviewed_plan"],
        }

    # Build the state graph
    workflow = StateGraph(LessonPlannerState)

    # Add nodes
    workflow.add_node("curriculum", curriculum_node)
    workflow.add_node("planner", lesson_planner_node)
    workflow.add_node("reviewer", lesson_reviewer_node)
    workflow.add_node("formatter", formatter_node)

    # Define the flow
    workflow.set_entry_point("curriculum")
    workflow.add_edge("curriculum", "planner")
    workflow.add_edge("planner", "reviewer")
    workflow.add_edge("reviewer", "formatter")
    workflow.add_edge("formatter", END)

    # Compile the graph
    app = workflow.compile()

    # Execute the workflow
    initial_state = {
        "messages": [],
        "user_prompt": user_prompt,
        "context": "",
        "standards": "",
        "lesson_plan": "",
        "reviewed_plan": "",
        "final_plan": "",
    }

    # Stream through the workflow and yield intermediate updates
    async for chunk in app.astream(initial_state):
        for node_name, state_update in chunk.items():
            # Surface meaningful updates as logs
            for key in ("standards", "lesson_plan", "reviewed_plan"):
                if state_update.get(key):
                    yield {
                        "type": "log",
                        "content": f"[{node_name}] {key}:\n{state_update[key]}",
                    }

            # Yield final plan as output (not log)
            if state_update.get("final_plan"):
                yield {
                    "type": "output",
                    "content": state_update["final_plan"],
                }


@context_params("prompt")
async def langgraph_lesson_planner(
    prompt: List[Dict[str, Any]],
) -> AsyncGenerator[ExecutionResult, None]:
    """
    MassGen custom tool wrapper for LangGraph lesson planner.

    This is the interface exposed to MassGen's backend. It handles environment setup,
    error handling, and wraps the core agent logic in ExecutionResult.

    Args:
        prompt: processed message list from orchestrator (auto-injected via execution_context)

    Returns:
        ExecutionResult containing the formatted lesson plan or error message
    """
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        yield ExecutionResult(
            output_blocks=[
                TextContent(data="Error: OPENAI_API_KEY not found. Please set the environment variable."),
            ],
        )
        return

    try:
        # Call the core agent function with processed messages and stream results
        async for result in run_langgraph_lesson_planner_agent(
            messages=prompt,
            api_key=api_key,
        ):
            if result["type"] == "log":
                # Yield intermediate updates as logs
                yield ExecutionResult(
                    output_blocks=[
                        TextContent(data=result["content"]),
                    ],
                    is_log=True,
                )
            else:  # type == "output"
                # Yield final plan as actual output
                yield ExecutionResult(
                    output_blocks=[
                        TextContent(data=f"LangGraph Lesson Planner Result:\n\n{result['content']}"),
                    ],
                )

    except Exception as e:
        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}"),
            ],
        )
