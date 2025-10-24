# -*- coding: utf-8 -*-
"""
AgentScope Lesson Planner Tool
This tool demonstrates interoperability by wrapping AgentScope's multi-agent framework as a MassGen custom tool.
Compatible with AgentScope 1.0.6+
"""

import os
from typing import Any, Dict, List

import agentscope
from agentscope.agent import AgentBase
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel

from massgen.tool._result import ExecutionResult, TextContent


class SimpleDialogAgent(AgentBase):
    """
    A simple dialog agent for AgentScope 1.0.6+
    This is a lightweight replacement for the deprecated DialogAgent.
    """

    def __init__(
        self,
        name: str,
        sys_prompt: str,
        model: OpenAIChatModel,
    ):
        """
        Initialize the dialog agent.

        Args:
            name: Agent name
            sys_prompt: System prompt for the agent
            model: OpenAI chat model instance
        """
        super().__init__()
        self.name = name
        self.sys_prompt = sys_prompt
        self.model = model
        self.formatter = OpenAIChatFormatter()
        self.memory = InMemoryMemory()

        # Store system prompt to add later (memory operations are async)
        self.pending_sys_msg = None
        if sys_prompt:
            self.pending_sys_msg = Msg(name="system", content=sys_prompt, role="system")

    async def reply(self, x: Msg = None) -> Msg:
        """
        Generate a reply to the input message.

        Args:
            x: Input message

        Returns:
            Response message
        """
        # Add system prompt on first call
        if self.pending_sys_msg is not None:
            await self.memory.add(self.pending_sys_msg)
            self.pending_sys_msg = None

        # Add user message to memory
        if x is not None:
            await self.memory.add(x)

        # Get conversation history
        history = await self.memory.get_memory()

        # Format messages for the model
        formatted_msgs = []
        for msg in history:
            formatted_msgs.append(
                {
                    "role": msg.role,
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                },
            )

        # Generate response using the model
        response = await self.model(formatted_msgs)

        # Extract content from ChatResponse
        # response.content is a list like [{'type': 'text', 'text': '...'}]
        content = ""
        if hasattr(response, "content") and isinstance(response.content, list):
            for item in response.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    content += item.get("text", "")
        elif hasattr(response, "content"):
            content = str(response.content)
        else:
            content = str(response)

        # Create response message
        response_msg = Msg(
            name=self.name,
            content=content,
            role="assistant",
        )

        # Add response to memory
        await self.memory.add(response_msg)

        return response_msg


async def run_agentscope_lesson_planner_agent(
    messages: List[Dict[str, Any]],
    api_key: str,
) -> str:
    """
    Core AgentScope lesson planner agent - pure AgentScope implementation.

    This function contains the pure AgentScope logic for creating lesson plans
    using multiple specialized DialogAgents in a sequential pipeline.

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

    # Extract the user's topic/request from messages
    # Messages is typically a list of dicts with 'role' and 'content'
    user_prompt = ""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            user_prompt = msg.get("content", "")
            break

    if not user_prompt:
        # Fallback: use the entire messages as string
        user_prompt = str(messages)

    # Initialize AgentScope (simplified for 1.0.6)
    agentscope.init(
        project="massgen_lesson_planner",
        name="agentscope_lesson_planner_run",
        logging_level="WARNING",
    )

    # Create shared model instance
    model = OpenAIChatModel(
        model_name="gpt-4o",
        api_key=api_key,
        stream=False,
        generate_kwargs={
            "temperature": 0.7,
        },
    )

    # Create specialized agents for each step
    curriculum_agent = SimpleDialogAgent(
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
        model=model,
    )

    lesson_planner_agent = SimpleDialogAgent(
        name="Lesson_Planning_Specialist",
        sys_prompt="""You are a lesson planning specialist.
Given standards and objectives, you create detailed lesson plans including:
- Opening/Hook (5-10 minutes)
- Main Activity (20-30 minutes)
- Practice Activity (15-20 minutes)
- Assessment/Closure (5-10 minutes)
Format as a structured lesson plan with clear timing and materials needed.""",
        model=model,
    )

    reviewer_agent = SimpleDialogAgent(
        name="Lesson_Plan_Reviewer",
        sys_prompt="""You are a lesson plan reviewer who ensures:
1. Age-appropriate content and activities
2. Alignment with provided standards
3. Realistic timing
4. Clear instructions
5. Differentiation opportunities
Provide an improved version of the lesson plan incorporating your feedback.""",
        model=model,
    )

    formatter_agent = SimpleDialogAgent(
        name="Lesson_Plan_Formatter",
        sys_prompt="""You are a lesson plan formatter. Format the complete plan as follows:
<title>Lesson plan title</title>
<standards>Standards covered</standards>
<learning_objectives>Key learning objectives</learning_objectives>
<materials>Materials required</materials>
<activities>Detailed lesson plan activities with timing</activities>
<assessment>Assessment details</assessment>""",
        model=model,
    )

    # Build the initial message
    initial_message = f"Please provide fourth grade standards and objectives for: {user_prompt}"

    # Create the sequential pipeline
    # Step 1: Get curriculum standards
    msg = Msg(name="User", content=initial_message, role="user")
    standards_response = await curriculum_agent.reply(msg)

    # Step 2: Create lesson plan based on standards
    lesson_msg = Msg(
        name="User",
        content=f"Based on these standards and objectives, create a detailed lesson plan:\n\n{standards_response.content}",
        role="user",
    )
    lesson_response = await lesson_planner_agent.reply(lesson_msg)

    # Step 3: Review and improve the lesson plan
    review_msg = Msg(
        name="User",
        content=f"Please review and improve this lesson plan:\n\n{lesson_response.content}",
        role="user",
    )
    reviewed_response = await reviewer_agent.reply(review_msg)

    # Step 4: Format the final lesson plan
    format_msg = Msg(
        name="User",
        content=f"Format this reviewed lesson plan:\n\n{reviewed_response.content}",
        role="user",
    )
    final_response = await formatter_agent.reply(format_msg)

    # Extract the final lesson plan
    lesson_plan = final_response.content if isinstance(final_response.content, str) else str(final_response.content)

    return lesson_plan


async def agentscope_lesson_planner(
    messages: List[Dict[str, Any]],
) -> ExecutionResult:
    """
    MassGen custom tool wrapper for AgentScope lesson planner.

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
        lesson_plan = await run_agentscope_lesson_planner_agent(
            messages=messages,
            api_key=api_key,
        )

        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"AgentScope Lesson Planner Result:\n\n{lesson_plan}"),
            ],
        )

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}\n\nDetails:\n{error_details}"),
            ],
        )
