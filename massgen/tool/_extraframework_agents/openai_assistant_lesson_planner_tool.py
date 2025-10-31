# -*- coding: utf-8 -*-
"""
OpenAI Assistant Lesson Planner Tool
This tool demonstrates interoperability by wrapping OpenAI's Assistants API as a MassGen custom tool.
"""

import asyncio
import os
from typing import Any, AsyncGenerator, Dict, List

from openai import AsyncOpenAI

from massgen.tool import context_params
from massgen.tool._result import ExecutionResult, TextContent


async def run_openai_assistant_lesson_planner_agent(
    messages: List[Dict[str, Any]],
    api_key: str,
) -> str:
    """
    Core OpenAI Assistant lesson planner agent - pure OpenAI Assistants API implementation.

    This function contains the pure OpenAI Assistants API logic for creating lesson plans
    using an assistant with specialized instructions.

    Args:
        messages: Complete message history from orchestrator
        api_key: OpenAI API key for the assistant

    Returns:
        The formatted lesson plan as a string

    Raises:
        Exception: Any errors during agent execution
    """
    if not messages:
        raise ValueError("No messages provided for lesson planning.")

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

    # Add a message to the thread
    await client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=f"Please create a comprehensive fourth grade lesson plan for: {messages}",
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
            raise Exception(f"Assistant run {run_status.status}")

        await asyncio.sleep(2)
        attempt += 1

    if attempt >= max_attempts:
        raise Exception("Assistant run timed out")

    # Retrieve the messages
    message_list = await client.beta.threads.messages.list(thread_id=thread.id)

    # Get the assistant's response (most recent message)
    lesson_plan = ""
    for message in message_list.data:
        if message.role == "assistant":
            for content in message.content:
                if hasattr(content, "text"):
                    lesson_plan = content.text.value
                    break
            break

    # Clean up - delete the assistant and thread
    await client.beta.assistants.delete(assistant.id)
    await client.beta.threads.delete(thread.id)

    return lesson_plan


@context_params("prompt")
async def openai_assistant_lesson_planner(
    prompt: List[Dict[str, Any]],
) -> AsyncGenerator[ExecutionResult, None]:
    """
    MassGen custom tool wrapper for OpenAI Assistant lesson planner.

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
        # Call the core agent function with processed messages
        lesson_plan = await run_openai_assistant_lesson_planner_agent(
            messages=prompt,
            api_key=api_key,
        )

        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"OpenAI Assistant Lesson Planner Result:\n\n{lesson_plan}"),
            ],
        )

    except Exception as e:
        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}"),
            ],
        )
