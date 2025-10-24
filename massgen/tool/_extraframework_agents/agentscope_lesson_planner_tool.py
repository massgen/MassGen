# -*- coding: utf-8 -*-
"""
AgentScope Lesson Planner Tool
This tool demonstrates interoperability by wrapping AgentScope's multi-agent framework as a MassGen custom tool.
"""

import os
from typing import Optional

import agentscope
from agentscope.agents import DialogAgent, UserAgent
from agentscope.message import Msg
from agentscope.pipelines import sequentialpipeline

from massgen.tool._result import ExecutionResult, TextContent


async def agentscope_lesson_planner(
    user_prompt: str,
    context: Optional[str] = None,
    system_message: Optional[str] = None,
    user_message: Optional[str] = None,
) -> ExecutionResult:
    """
    Create a comprehensive lesson plan using AgentScope's multi-agent framework.

    This tool uses AgentScope to orchestrate multiple specialized agents to:
    1. Determine curriculum standards and learning objectives
    2. Create a detailed lesson plan
    3. Review and refine the plan
    4. Format the final lesson plan in a standardized format

    Args:
        user_prompt: The user's request
        context: Additional context or background information (optional)
        system_message: System message from orchestrator (optional, auto-injected)
        user_message: User message from orchestrator (optional, auto-injected)

    Returns:
        ExecutionResult containing the formatted lesson plan
    """
    # Optional: Use messages from orchestrator for additional context
    _ = system_message  # Available but not used in this implementation
    _ = user_message  # Available but not used in this implementation

    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return ExecutionResult(
            output_blocks=[
                TextContent(data="Error: OPENAI_API_KEY not found. Please set the environment variable."),
            ],
        )

    try:
        # Initialize AgentScope
        agentscope.init(
            model_configs=[
                {
                    "model_type": "openai_chat",
                    "config_name": "gpt-4o",
                    "model_name": "gpt-4o",
                    "api_key": api_key,
                    "organization": None,
                    "generate_args": {
                        "temperature": 0.7,
                    },
                },
            ],
        )

        # Create specialized agents for each step
        curriculum_agent = DialogAgent(
            name="Curriculum_Standards_Expert",
            sys_prompt="""You are a curriculum standards expert for fourth grade education.
When given a topic, you provide relevant grade-level standards and learning objectives.
Format every response as:
STANDARDS:
- [Standard 1]
- [Standard 2]
OBJECTIVES:
- By the end of this lesson, students will be able to [objective 1]
- By the end of this lesson, students will be able to [objective 2]""",
            model_config_name="gpt-4o",
        )

        lesson_planner_agent = DialogAgent(
            name="Lesson_Planning_Specialist",
            sys_prompt="""You are a lesson planning specialist.
Given standards and objectives, you create detailed lesson plans including:
- Opening/Hook (5-10 minutes)
- Main Activity (20-30 minutes)
- Practice Activity (15-20 minutes)
- Assessment/Closure (5-10 minutes)
Format as a structured lesson plan with clear timing and materials needed.""",
            model_config_name="gpt-4o",
        )

        reviewer_agent = DialogAgent(
            name="Lesson_Plan_Reviewer",
            sys_prompt="""You are a lesson plan reviewer who ensures:
1. Age-appropriate content and activities
2. Alignment with provided standards
3. Realistic timing
4. Clear instructions
5. Differentiation opportunities
Provide an improved version of the lesson plan incorporating your feedback.""",
            model_config_name="gpt-4o",
        )

        formatter_agent = DialogAgent(
            name="Lesson_Plan_Formatter",
            sys_prompt="""You are a lesson plan formatter. Format the complete plan as follows:
<title>Lesson plan title</title>
<standards>Standards covered</standards>
<learning_objectives>Key learning objectives</learning_objectives>
<materials>Materials required</materials>
<activities>Detailed lesson plan activities with timing</activities>
<assessment>Assessment details</assessment>""",
            model_config_name="gpt-4o",
        )

        # Build the initial message with context
        initial_message = f"Please provide fourth grade standards and objectives for: {user_prompt}"
        if context:
            initial_message += f"\n\nAdditional Context: {context}"

        # Create the sequential pipeline
        # Step 1: Get curriculum standards
        msg = Msg(name="User", content=initial_message, role="user")
        standards_response = curriculum_agent(msg)

        # Step 2: Create lesson plan based on standards
        lesson_msg = Msg(
            name="User",
            content=f"Based on these standards and objectives, create a detailed lesson plan:\n\n{standards_response.content}",
            role="user",
        )
        lesson_response = lesson_planner_agent(lesson_msg)

        # Step 3: Review and improve the lesson plan
        review_msg = Msg(
            name="User",
            content=f"Please review and improve this lesson plan:\n\n{lesson_response.content}",
            role="user",
        )
        reviewed_response = reviewer_agent(review_msg)

        # Step 4: Format the final lesson plan
        format_msg = Msg(
            name="User",
            content=f"Format this reviewed lesson plan:\n\n{reviewed_response.content}",
            role="user",
        )
        final_response = formatter_agent(format_msg)

        # Extract the final lesson plan
        lesson_plan = final_response.content

        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"AgentScope Lesson Planner Result for '{user_prompt}':\n\n{lesson_plan}"),
            ],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}"),
            ],
        )
