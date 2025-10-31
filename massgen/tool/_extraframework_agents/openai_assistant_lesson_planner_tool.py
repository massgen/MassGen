# -*- coding: utf-8 -*-
"""
OpenAI Assistant Lesson Planner Tool (Multi-Agent Streaming Version)
This tool demonstrates interoperability by wrapping OpenAI's Chat Completions API with streaming support
and multi-agent collaboration pattern similar to AG2.
"""

import os
from typing import Any, AsyncGenerator, Dict, List
from openai import AsyncOpenAI

from massgen.tool import context_params
from massgen.tool._result import ExecutionResult, TextContent


# Define role-specific system prompts (similar to AG2 agents)
CURRICULUM_AGENT_PROMPT = """You are a curriculum standards expert for fourth grade education.
When given a topic, you provide relevant grade-level standards and learning objectives.
Format every response as:
STANDARDS:
- [Standard 1]
- [Standard 2]
OBJECTIVES:
- By the end of this lesson, students will be able to [objective 1]
- By the end of this lesson, students will be able to [objective 2]"""

LESSON_PLANNER_AGENT_PROMPT = """You are a lesson planning specialist.
Given standards and objectives, you create detailed lesson plans including:
- Opening/Hook (5-10 minutes)
- Main Activity (20-30 minutes)
- Practice Activity (15-20 minutes)
- Assessment/Closure (5-10 minutes)
Format as a structured lesson plan with clear timing and materials needed."""

LESSON_REVIEWER_AGENT_PROMPT = """You are a lesson plan reviewer who ensures:
1. Age-appropriate content and activities
2. Alignment with provided standards
3. Realistic timing
4. Clear instructions
5. Differentiation opportunities
Provide specific feedback in these areas and suggest improvements if needed."""

LESSON_FORMATTER_AGENT_PROMPT = """You are a lesson plan formatter. Format the complete plan as follows:
<title>Lesson plan title</title>
<standards>Standards covered</standards>
<learning_objectives>Key learning objectives</learning_objectives>
<materials>Materials required</materials>
<activities>Detailed lesson plan activities with timing</activities>
<assessment>Assessment details</assessment>"""


async def run_agent_step(
    client: AsyncOpenAI,
    role_prompt: str,
    user_message: str,
    temperature: float = 0.7,
) -> str:
    """
    Run a single agent step with streaming and collect the full response.

    Args:
        client: AsyncOpenAI client
        role_prompt: System prompt for this agent role
        user_message: User message to process
        temperature: Temperature for generation

    Returns:
        Complete response from the agent
    """
    messages = [
        {"role": "system", "content": role_prompt},
        {"role": "user", "content": user_message},
    ]

    stream = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        stream=True,
        temperature=temperature,
    )

    full_response = ""
    async for chunk in stream:
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta.content:
                full_response += delta.content

    return full_response


@context_params("prompt")
async def openai_assistant_lesson_planner(
    prompt: List[Dict[str, Any]],
) -> AsyncGenerator[ExecutionResult, None]:
    """
    MassGen custom tool wrapper for OpenAI lesson planner with multi-agent collaboration.

    This version uses multiple specialized agents (similar to AG2) to collaboratively create
    a lesson plan through sequential steps:
    1. Curriculum Agent: Identifies standards and objectives
    2. Lesson Planner Agent: Creates the detailed lesson plan
    3. Lesson Reviewer Agent: Reviews and provides feedback
    4. Formatter Agent: Formats the final plan

    Args:
        prompt: processed message list from orchestrator (auto-injected via execution_context)

    Yields:
        ExecutionResult containing text chunks as they arrive, or error messages
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

    if not prompt:
        yield ExecutionResult(
            output_blocks=[
                TextContent(data="Error: No messages provided for lesson planning."),
            ],
        )
        return

    try:
        # Initialize OpenAI client
        client = AsyncOpenAI(api_key=api_key)

        # Extract the user's request
        user_request = str(prompt)

        # Yield an initial message
        yield ExecutionResult(
            output_blocks=[
                TextContent(data="OpenAI Lesson Planner (Multi-Agent Collaboration):\n\n"),
            ],
        )

        # Step 1: Curriculum Agent - Determine standards and objectives
        yield ExecutionResult(
            output_blocks=[
                TextContent(data="[Curriculum Agent] Identifying standards and objectives...\n"),
            ],
            is_log=True,
        )

        standards_and_objectives = await run_agent_step(
            client,
            CURRICULUM_AGENT_PROMPT,
            f"Please provide fourth grade standards and objectives for: {user_request}",
        )

        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"{standards_and_objectives}\n\n"),
            ],
            is_log=True,
        )

        # Step 2: Lesson Planner Agent - Create detailed lesson plan
        yield ExecutionResult(
            output_blocks=[
                TextContent(data="[Lesson Planner Agent] Creating detailed lesson plan...\n"),
            ],
            is_log=True,
        )

        lesson_plan = await run_agent_step(
            client,
            LESSON_PLANNER_AGENT_PROMPT,
            f"Based on these standards and objectives:\n{standards_and_objectives}\n\nCreate a detailed lesson plan for: {user_request}",
        )

        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"{lesson_plan}\n\n"),
            ],
            is_log=True,
        )

        # Step 3: Lesson Reviewer Agent - Review and provide feedback
        yield ExecutionResult(
            output_blocks=[
                TextContent(data="[Lesson Reviewer Agent] Reviewing lesson plan...\n"),
            ],
            is_log=True,
        )

        review_feedback = await run_agent_step(
            client,
            LESSON_REVIEWER_AGENT_PROMPT,
            f"Review this lesson plan:\n{lesson_plan}\n\nProvide feedback and suggest improvements.",
        )

        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"{review_feedback}\n\n"),
            ],
            is_log=True,
        )

        # Step 4: Formatter Agent - Format the final plan with streaming
        yield ExecutionResult(
            output_blocks=[
                TextContent(data="[Formatter Agent] Formatting final lesson plan...\n\n"),
            ],
            is_log=True,
        )

        messages = [
            {"role": "system", "content": LESSON_FORMATTER_AGENT_PROMPT},
            {"role": "user", "content": f"Format this complete lesson plan:\n\nStandards and Objectives:\n{standards_and_objectives}\n\nLesson Plan:\n{lesson_plan}\n\nReview Feedback:\n{review_feedback}"},
        ]

        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            stream=True,
            temperature=0.7,
        )

        # Stream the final formatted output
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield ExecutionResult(
                        output_blocks=[
                            TextContent(data=delta.content),
                        ],
                    )

    except Exception as e:
        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"\nError during lesson planning: {str(e)}"),
            ],
        )
