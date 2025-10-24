# -*- coding: utf-8 -*-
"""
SmolAgent Lesson Planner Tool
This tool demonstrates interoperability by wrapping HuggingFace's SmolAgent framework as a MassGen custom tool.
"""

import os
from typing import Optional

from smolagents import CodeAgent, LiteLLMModel, tool

from massgen.tool._result import ExecutionResult, TextContent


async def smolagent_lesson_planner(user_prompt: str, context: Optional[str] = None) -> ExecutionResult:
    """
    Create a comprehensive lesson plan using HuggingFace's SmolAgent framework.

    This tool uses SmolAgent with custom tools to:
    1. Determine curriculum standards and learning objectives
    2. Create a detailed lesson plan
    3. Review and refine the plan
    4. Format the final lesson plan in a standardized format

    Args:
        user_prompt: The user's request or lesson topic (e.g., "photosynthesis", "fractions")
        context: Additional context or background information (optional)

    Returns:
        ExecutionResult containing the formatted lesson plan
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
            return f"""Format this lesson plan with the following structure:
<title>Lesson plan title</title>
<standards>Standards covered</standards>
<learning_objectives>Key learning objectives</learning_objectives>
<materials>Materials required</materials>
<activities>Detailed lesson plan activities with timing</activities>
<assessment>Assessment details</assessment>

Lesson plan to format: {lesson_plan}"""

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

        # Build the task with context if provided
        task = f"Create a comprehensive fourth grade lesson plan for: {user_prompt}"
        if context:
            task += f"\n\nAdditional Context: {context}"

        task += """

Please follow these steps:
1. Use get_curriculum_standards to identify relevant standards
2. Use create_lesson_plan to create a detailed plan
3. Use review_lesson_plan to review and improve the plan
4. Use format_lesson_plan to format the final output

The final plan should include:
- Opening/Hook (5-10 minutes)
- Main Activity (20-30 minutes)
- Practice Activity (15-20 minutes)
- Assessment/Closure (5-10 minutes)"""

        # Run the agent
        result = agent.run(task)

        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"SmolAgent Lesson Planner Result for '{user_prompt}':\n\n{result}"),
            ],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}"),
            ],
        )
