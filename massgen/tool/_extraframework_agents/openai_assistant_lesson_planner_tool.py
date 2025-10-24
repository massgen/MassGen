# -*- coding: utf-8 -*-
"""
OpenAI Assistant Lesson Planner Tool
This tool demonstrates interoperability by wrapping OpenAI's Assistants API as a MassGen custom tool.
"""

import asyncio
import os
from typing import Optional

from openai import AsyncOpenAI

from massgen.tool._result import ExecutionResult, TextContent


async def openai_assistant_lesson_planner(
    user_prompt: str,
    context: Optional[str] = None,
    system_message: Optional[str] = None,
    user_message: Optional[str] = None,
) -> ExecutionResult:
    """
    Create a comprehensive lesson plan using OpenAI's Assistants API.

    This tool uses OpenAI Assistants with custom instructions to:
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
        # Initialize OpenAI client
        client = AsyncOpenAI(api_key=api_key)

        # Create an assistant with specialized instructions
        assistant = await client.beta.assistants.create(
            name="Lesson Planner Assistant",
            instructions="""You are an expert fourth grade lesson planner. When given a topic, you should:

1. First, identify relevant curriculum standards and learning objectives for fourth grade
2. Create a detailed lesson plan including:
   - Opening/Hook (5-10 minutes)
   - Main Activity (20-30 minutes)
   - Practice Activity (15-20 minutes)
   - Assessment/Closure (5-10 minutes)
3. Review the plan for age-appropriateness, timing, and engagement
4. Format the final plan using this structure:

<title>Lesson plan title</title>
<standards>Standards covered</standards>
<learning_objectives>Key learning objectives</learning_objectives>
<materials>Materials required</materials>
<activities>Detailed lesson plan activities with timing</activities>
<assessment>Assessment details</assessment>

Ensure the lesson plan is practical, engaging, and aligned with fourth grade standards.""",
            model="gpt-4o",
        )

        # Create a thread
        thread = await client.beta.threads.create()

        # Build the message with context if provided
        message_content = user_prompt
        if context:
            message_content = f"{user_prompt}\n\nAdditional Context: {context}"

        # Add a message to the thread
        await client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"Please create a comprehensive fourth grade lesson plan for: {message_content}",
        )

        # Run the assistant
        run = await client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id,
        )

        # Wait for completion
        max_attempts = 30
        attempt = 0
        while attempt < max_attempts:
            run_status = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            if run_status.status == "completed":
                break
            elif run_status.status in ["failed", "cancelled", "expired"]:
                return ExecutionResult(
                    output_blocks=[
                        TextContent(data=f"Error: Assistant run {run_status.status}"),
                    ],
                )

            await asyncio.sleep(2)
            attempt += 1

        if attempt >= max_attempts:
            return ExecutionResult(
                output_blocks=[
                    TextContent(data="Error: Assistant run timed out"),
                ],
            )

        # Retrieve the messages
        messages = await client.beta.threads.messages.list(thread_id=thread.id)

        # Get the assistant's response (most recent message)
        lesson_plan = ""
        for message in messages.data:
            if message.role == "assistant":
                for content in message.content:
                    if hasattr(content, "text"):
                        lesson_plan = content.text.value
                        break
                break

        # Clean up - delete the assistant and thread
        await client.beta.assistants.delete(assistant.id)
        await client.beta.threads.delete(thread.id)

        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"OpenAI Assistant Lesson Planner Result for '{user_prompt}':\n\n{lesson_plan}"),
            ],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}"),
            ],
        )
