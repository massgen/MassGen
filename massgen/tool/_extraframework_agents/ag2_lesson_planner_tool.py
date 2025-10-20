# -*- coding: utf-8 -*-
"""
AG2 (AutoGen) Nested Chat Lesson Planner Tool
This tool demonstrates interoperability by wrapping AutoGen's nested chat functionality as a MassGen custom tool.
"""

from autogen import ConversableAgent, GroupChatManager, GroupChat
from massgen.tool._result import ExecutionResult, TextContent
import os
from typing import Optional


async def ag2_lesson_planner(topic: str, api_key: Optional[str] = None) -> ExecutionResult:
    """
    Create a comprehensive lesson plan using AG2's nested chat architecture.

    This tool uses multiple AutoGen agents in a nested chat structure to:
    1. Determine curriculum standards and learning objectives
    2. Create a detailed lesson plan through collaborative group chat
    3. Format the final lesson plan in a standardized format

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
        # Configure LLM
        llm_config = {
            "config_list": [{
                "api_type": "openai",
                "model": "gpt-4o",
                "api_key": api_key
            }]
        }

        # Curriculum Standards Agent
        curriculum_agent = ConversableAgent(
            name="Curriculum_Agent",
            system_message="""You are a curriculum standards expert for fourth grade education.
            When given a topic, you provide relevant grade-level standards and learning objectives.
            Format every response as:
            STANDARDS:
            - [Standard 1]
            - [Standard 2]
            OBJECTIVES:
            - By the end of this lesson, students will be able to [objective 1]
            - By the end of this lesson, students will be able to [objective 2]""",
            human_input_mode="NEVER",
            llm_config=llm_config,
        )

        # Lesson Planner Agent
        lesson_planner_agent = ConversableAgent(
            name="Lesson_Planner_Agent",
            system_message="""You are a lesson planning specialist.
            Given standards and objectives, you create detailed lesson plans including:
            - Opening/Hook (5-10 minutes)
            - Main Activity (20-30 minutes)
            - Practice Activity (15-20 minutes)
            - Assessment/Closure (5-10 minutes)
            Format as a structured lesson plan with clear timing and materials needed.""",
            human_input_mode="NEVER",
            llm_config=llm_config,
        )

        # Lesson Reviewer Agent
        lesson_reviewer_agent = ConversableAgent(
            name="Lesson_Reviewer_Agent",
            system_message="""You are a lesson plan reviewer who ensures:
            1. Age-appropriate content and activities
            2. Alignment with provided standards
            3. Realistic timing
            4. Clear instructions
            5. Differentiation opportunities
            Provide specific feedback in these areas and suggest improvements if needed.""",
            human_input_mode="NEVER",
            llm_config=llm_config,
        )

        # Lead Teacher Agent
        lead_teacher_agent = ConversableAgent(
            name="Lead_Teacher_Agent",
            system_message="""You are an experienced fourth grade teacher who oversees the lesson planning process.
            Your role is to:
            1. Initiate the planning process with a clear topic
            2. Review and integrate feedback from other agents
            3. Ensure the final lesson plan is practical and engaging
            4. Make final adjustments based on classroom experience""",
            human_input_mode="NEVER",
            llm_config=llm_config,
        )

        # Create the group chat for collaborative lesson planning
        planning_chat = GroupChat(
            agents=[curriculum_agent, lesson_planner_agent, lesson_reviewer_agent],
            messages=[],
            max_round=4,
            send_introductions=True,
        )

        planning_manager = GroupChatManager(
            groupchat=planning_chat,
            llm_config=llm_config,
        )

        # Formatter of the final lesson plan to a standard format
        formatter_message = """You are a lesson plan formatter. Format the complete plan as follows:
<title>Lesson plan title</title>
<standards>Standards covered</standards>
<learning_objectives>Key learning objectives</learning_objectives>
<materials>Materials required</materials>
<activities>Lesson plan activities</activities>
<assessment>Assessment details</assessment>
"""

        lesson_formatter = ConversableAgent(
            name="formatter_agent",
            system_message=formatter_message,
            llm_config=llm_config,
        )

        # Create nested chats configuration
        nested_chats = [
            {
                # The first internal chat determines the standards and objectives
                "recipient": curriculum_agent,
                "message": f"Please provide fourth grade standards and objectives for the topic: {topic}",
                "max_turns": 2,
                "summary_method": "last_msg",
            },
            {
                # A group chat follows, where the lesson plan is created
                "recipient": planning_manager,
                "message": "Based on these standards and objectives, create a detailed lesson plan.",
                "max_turns": 1,
                "summary_method": "last_msg",
            },
            {
                # Finally, a two-agent chat formats the lesson plan
                "recipient": lesson_formatter,
                "message": "Format the lesson plan.",
                "max_turns": 1,
                "summary_method": "last_msg",
            }
        ]

        # Register nested chats with the lead teacher
        lead_teacher_agent.register_nested_chats(
            chat_queue=nested_chats,
            trigger=lambda sender: sender.name == "Assistant_Agent",
        )

        # Create a simple assistant agent to trigger the nested chat
        assistant_agent = ConversableAgent(
            name="Assistant_Agent",
            system_message="You are a helpful assistant.",
            human_input_mode="NEVER",
            llm_config=llm_config,
        )

        # Initiate the chat and get the result
        result = assistant_agent.initiate_chat(
            recipient=lead_teacher_agent,
            message=f"Create a lesson plan for: {topic}",
            max_turns=1
        )

        # Extract the lesson plan from the result
        lesson_plan = result.summary if hasattr(result, 'summary') else str(result)

        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"AG2 Lesson Planner Result for '{topic}':\n\n{lesson_plan}"),
            ],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"Error creating lesson plan: {str(e)}"),
            ],
        )
