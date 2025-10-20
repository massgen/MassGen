# -*- coding: utf-8 -*-
"""
LangGraph Lesson Planner Tool
This tool demonstrates interoperability by wrapping LangGraph's state graph functionality as a MassGen custom tool.
"""

import operator
import os
from typing import Annotated, Optional, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from massgen.tool._result import ExecutionResult, TextContent


class LessonPlannerState(TypedDict):
    """State for the lesson planner workflow."""

    messages: Annotated[Sequence[BaseMessage], operator.add]
    topic: str
    standards: str
    lesson_plan: str
    reviewed_plan: str
    final_plan: str


async def langgraph_lesson_planner(topic: str, api_key: Optional[str] = None) -> ExecutionResult:
    """
    Create a comprehensive lesson plan using LangGraph's state graph architecture.

    This tool uses LangGraph to orchestrate multiple AI agents in a sequential workflow to:
    1. Determine curriculum standards and learning objectives
    2. Create a detailed lesson plan
    3. Review and refine the lesson plan
    4. Format the final lesson plan in a standardized format

    Args:
        topic: The lesson topic to create a plan for (e.g., "photosynthesis", "fractions")
        api_key: OpenAI API key (optional, will use OPENAI_API_KEY env var if not provided)

    Returns:
        ExecutionResult containing the formatted lesson plan
    """
    # Get API key from parameter or environment
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return ExecutionResult(
            output_blocks=[
                TextContent(data="Error: OPENAI_API_KEY not found. Please set the environment variable or pass it as a parameter."),
            ],
        )

    try:
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

            human_msg = HumanMessage(content=f"Please provide fourth grade standards and objectives for the topic: {state['topic']}")

            messages = [system_msg, human_msg]
            response = await llm.ainvoke(messages)

            return {
                "messages": [response],
                "standards": response.content,
                "topic": state["topic"],
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

            messages = [system_msg, human_msg]
            response = await llm.ainvoke(messages)

            return {
                "messages": state["messages"] + [response],
                "lesson_plan": response.content,
                "topic": state["topic"],
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

            messages = [system_msg, human_msg]
            response = await llm.ainvoke(messages)

            return {
                "messages": state["messages"] + [response],
                "reviewed_plan": response.content,
                "topic": state["topic"],
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

            messages = [system_msg, human_msg]
            response = await llm.ainvoke(messages)

            return {
                "messages": state["messages"] + [response],
                "final_plan": response.content,
                "topic": state["topic"],
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
            "topic": topic,
            "standards": "",
            "lesson_plan": "",
            "reviewed_plan": "",
            "final_plan": "",
        }

        # Stream intermediate results
        output_parts = [f"LangGraph Lesson Planner - Streaming Progress for '{topic}':\n"]
        final_state = None

        async for chunk in app.astream(initial_state):
            for node_name, state_update in chunk.items():
                output_parts.append(f"\n✓ Node '{node_name}' completed")

                # Show intermediate results for each node
                if node_name == "curriculum" and state_update.get("standards"):
                    output_parts.append(f"\n  Standards identified:\n  {state_update['standards'][:200]}...")
                elif node_name == "planner" and state_update.get("lesson_plan"):
                    output_parts.append(f"\n  Lesson plan created: {len(state_update['lesson_plan'])} characters")
                elif node_name == "reviewer" and state_update.get("reviewed_plan"):
                    output_parts.append(f"\n  Review completed: {len(state_update['reviewed_plan'])} characters")
                elif node_name == "formatter" and state_update.get("final_plan"):
                    output_parts.append("\n  Final formatting completed")
                    final_state = state_update

        # Extract the final lesson plan
        lesson_plan = final_state.get("final_plan", "No lesson plan generated") if final_state else "No lesson plan generated"

        output_parts.append(f"\n\n{'='*60}\nFinal Lesson Plan:\n{'='*60}\n\n{lesson_plan}")

        return ExecutionResult(
            output_blocks=[
                TextContent(data="".join(output_parts)),
            ],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}"),
            ],
        )
