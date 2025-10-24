# -*- coding: utf-8 -*-
"""
SmolAgent Lesson Planner Tool
This tool demonstrates interoperability by wrapping HuggingFace's SmolAgent framework as a MassGen custom tool.
"""

import os
from typing import Any, Dict, List

from smolagents import CodeAgent, LiteLLMModel, tool

from massgen.tool._result import ExecutionResult, TextContent


def run_smolagent_lesson_planner_agent(
    messages: List[Dict[str, Any]],
    api_key: str,
) -> str:
    """
    Core SmolAgent lesson planner agent - pure SmolAgent implementation.

    This function contains the pure SmolAgent logic for creating lesson plans
    using custom tools and CodeAgent.

    Args:
        messages: Complete message history from orchestrator
        api_key: OpenAI API key for the agents

    Returns:
        The formatted lesson plan as a string

    Raises:
        Exception: Any errors during agent execution
    """
    if not messages:
        raise ValueError("No messages provided for lesson planning.")

    # Define custom tools for the lesson planning workflow
    @tool
    def get_curriculum_standards(topic: str) -> str:
        """
        Determine fourth grade curriculum standards and learning objectives for a given topic.

        Args:
            topic: The lesson topic to get standards for

        Returns:
            A formatted string with standards and objectives
        """
        # This tool would interact with the LLM to generate standards
        return f"Generate fourth grade curriculum standards and learning objectives for: {topic}"

    @tool
    def create_lesson_plan(topic: str, standards: str) -> str:
        """
        Create a detailed lesson plan based on topic and standards.

        Args:
            topic: The lesson topic
            standards: The curriculum standards and objectives

        Returns:
            A detailed lesson plan with activities and timing
        """
        return f"Create a detailed lesson plan for '{topic}' based on these standards: {standards}"

    @tool
    def review_lesson_plan(lesson_plan: str) -> str:
        """
        Review a lesson plan for age-appropriateness, timing, and engagement.

        Args:
            lesson_plan: The lesson plan to review

        Returns:
            An improved version of the lesson plan
        """
        return f"Review and improve this lesson plan: {lesson_plan}"

    @tool
    def format_lesson_plan(lesson_plan: str) -> str:
        """
        Format a lesson plan to a standardized structure.

        Args:
            lesson_plan: The lesson plan to format

        Returns:
            A formatted lesson plan with XML-like tags
        """
        return (
            f"Format this lesson plan with the following structure:\n"
            f"<title>Lesson plan title</title>\n"
            f"<standards>Standards covered</standards>\n"
            f"<learning_objectives>Key learning objectives</learning_objectives>\n"
            f"<materials>Materials required</materials>\n"
            f"<activities>Detailed lesson plan activities with timing</activities>\n"
            f"<assessment>Assessment details</assessment>\n\n"
            f"Lesson plan to format: {lesson_plan}"
        )

    # Initialize the model
    model = LiteLLMModel(
        model_id="openai/gpt-4o",
        api_key=api_key,
    )

    # Create the agent with custom tools
    agent = CodeAgent(
        tools=[get_curriculum_standards, create_lesson_plan, review_lesson_plan, format_lesson_plan],
        model=model,
        max_steps=10,
    )

    # Build the task from messages
    task = f"Create a comprehensive fourth grade lesson plan for: {messages}\n\n"
    task += "Please follow these steps:\n"
    task += "1. Use get_curriculum_standards to identify relevant standards\n"
    task += "2. Use create_lesson_plan to create a detailed plan\n"
    task += "3. Use review_lesson_plan to review and improve the plan\n"
    task += "4. Use format_lesson_plan to format the final output\n\n"
    task += "The final plan should include:\n"
    task += "- Opening/Hook (5-10 minutes)\n"
    task += "- Main Activity (20-30 minutes)\n"
    task += "- Practice Activity (15-20 minutes)\n"
    task += "- Assessment/Closure (5-10 minutes)"

    # Run the agent
    result = agent.run(task)

    return result


async def smolagent_lesson_planner(
    messages: List[Dict[str, Any]],
) -> ExecutionResult:
    """
    MassGen custom tool wrapper for SmolAgent lesson planner.

    This is the interface exposed to MassGen's backend. It handles environment setup,
    error handling, and wraps the core agent logic in ExecutionResult.

    Args:
        messages: Complete message list from orchestrator (auto-injected via execution_context)

    Returns:
        ExecutionResult containing the formatted lesson plan or error message
    """
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return ExecutionResult(
            output_blocks=[
                TextContent(data="Error: OPENAI_API_KEY not found. Please set the environment variable."),
            ],
        )

    try:
        # Call the core agent function with complete messages
        lesson_plan = run_smolagent_lesson_planner_agent(
            messages=messages,
            api_key=api_key,
        )

        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"SmolAgent Lesson Planner Result:\n\n{lesson_plan}"),
            ],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}"),
            ],
        )
