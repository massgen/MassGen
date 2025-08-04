"""
MassAgent implementations that wrap the existing agent backends.

This module provides MassAgent-compatible wrappers for the existing
OpenAI, Gemini, and Grok agent implementations.
"""

import os
import sys
import copy
import time
import traceback
from typing import Callable, Union, Optional, List, Dict, Any

from dotenv import load_dotenv

load_dotenv()

from .agent import MassAgent
from .types import ModelConfig, TaskInput
from .tools import register_tool


class OpenAIMassAgent(MassAgent):
    """MassAgent wrapper for OpenAI agent implementation."""

    def __init__(
        self,
        agent_id: int,
        orchestrator=None,
        model_config: Optional[ModelConfig] = None,
        stream_callback: Optional[Callable] = None,
        **kwargs,
    ):

        # Pass all configuration to parent, including agent_type
        super().__init__(
            agent_id=agent_id,
            orchestrator=orchestrator,
            model_config=model_config,
            stream_callback=stream_callback,
            **kwargs,
        )


class GrokMassAgent(OpenAIMassAgent):
    """MassAgent wrapper for Grok agent implementation."""

    def __init__(
        self,
        agent_id: int,
        orchestrator=None,
        model_config: Optional[ModelConfig] = None,
        stream_callback: Optional[Callable] = None,
        **kwargs,
    ):

        # Pass all configuration to parent, including agent_type
        super().__init__(
            agent_id=agent_id,
            orchestrator=orchestrator,
            model_config=model_config,
            stream_callback=stream_callback,
            **kwargs,
        )


class GeminiMassAgent(OpenAIMassAgent):
    """MassAgent wrapper for Gemini agent implementation."""

    def __init__(
        self,
        agent_id: int,
        orchestrator=None,
        model_config: Optional[ModelConfig] = None,
        stream_callback: Optional[Callable] = None,
        **kwargs,
    ):

        # Pass all configuration to parent, including agent_type
        super().__init__(
            agent_id=agent_id,
            orchestrator=orchestrator,
            model_config=model_config,
            stream_callback=stream_callback,
            **kwargs,
        )

    def _get_curr_messages_and_tools(self, task: TaskInput):
        """Get the current messages and tools for the agent."""
        # Get available tools (system tools + built-in tools + custom tools)
        system_tools = self._get_system_tools()
        built_in_tools = self._get_builtin_tools()
        custom_tools = self._get_registered_tools()

        # Gemini does not support built-in tools and function call at the same time.
        # If built-in tools are provided, we will switch to them in the next round.
        tool_switch = bool(built_in_tools)

        # We provide built-in tools in the first round, and then custom tools in the next round.
        if tool_switch:
            function_call_enabled = False
            available_tools = built_in_tools
        else:
            function_call_enabled = True
            available_tools = system_tools + custom_tools

        # Initialize working messages
        working_status, user_input = self._get_task_input(task)
        working_messages = self._get_task_input_messages(user_input)

        return (
            working_status,
            working_messages,
            available_tools,
            system_tools,
            custom_tools,
            built_in_tools,
            tool_switch,
            function_call_enabled,
        )

    def work_on_task(self, task: TaskInput) -> List[Dict[str, str]]:
        """
        Work on the task using the Gemini backend with conversation continuation.

        NOTE:
        Gemini's does not support built-in tools and function call at the same time.
        Therefore, we provide them interchangedly in different rounds.
        The way the conversation is constructed is also different from OpenAI.
        You can provide consecutive user messages to represent the function call results.

        Args:
            task: The task to work on
            messages: Current conversation history
            restart_instruction: Optional instruction for restarting work (e.g., updates from other agents)

        Returns:
            Updated conversation history including agent's work
        """
        curr_round = 0
        (
            working_status,
            working_messages,
            available_tools,
            system_tools,
            custom_tools,
            built_in_tools,
            tool_switch,
            function_call_enabled,
        ) = self._get_curr_messages_and_tools(task)

        # Start the task solving loop
        while curr_round < self.max_rounds and self.state.status == "working":
            try:
                # If function call is enabled or not, add a notification to the user
                if working_messages[-1].get("role", "") == "user":
                    if not function_call_enabled:
                        working_messages[-1]["content"] += (
                            "\n\n"
                            + "Note that the `add_answer` and `vote` tools are not enabled now. Please prioritize using the built-in tools to analyze the task first."
                        )
                    else:
                        working_messages[-1]["content"] += (
                            "\n\n"
                            + "Note that the `add_answer` and `vote` tools are enabled now."
                        )

                # Call LLM with current conversation
                result = self.process_message(
                    messages=working_messages, tools=available_tools
                )

                # Before Making the new result into effect, check if there is any update from other agents that are unseen by this agent
                agents_with_update = self.check_update()
                has_update = len(agents_with_update) > 0
                # Case 1: if vote() is called and there are new update: make it invalid and renew the conversation
                # Case 2: if add_answer() is called and there are new update: make it valid and renew the conversation
                # Case 3: if no function call is made and there are new update: renew the conversation

                # Add assistant response
                if result.text:
                    working_messages.append(
                        {"role": "assistant", "content": result.text}
                    )

                # Execute function calls if any
                if result.function_calls:
                    # Deduplicate function calls by their name
                    result.function_calls = self.deduplicate_function_calls(
                        result.function_calls
                    )
                    function_outputs, successful_called = self._execute_function_calls(
                        result.function_calls, invalid_vote_options=agents_with_update
                    )

                    renew_conversation = False
                    for function_call, function_output, successful_called in zip(
                        result.function_calls, function_outputs, successful_called
                    ):
                        # If call `add_answer`, we need to rebuild the conversation history with new answers
                        if (
                            function_call.get("name") == "add_answer"
                            and successful_called
                        ):
                            renew_conversation = True
                            break

                        # If call `vote`, we need to break the loop
                        if function_call.get("name") == "vote" and successful_called:
                            renew_conversation = True
                            break

                    if not renew_conversation:
                        # Add all function call results to the current conversation
                        for function_call, function_output in zip(
                            result.function_calls, function_outputs
                        ):
                            working_messages.extend([function_call, function_output])
                        # If we have used custom tools, switch to built-in tools in the next round
                        if tool_switch:
                            available_tools = built_in_tools
                            function_call_enabled = False
                            print(
                                f"🔄 Agent {self.agent_id} (Gemini) switching to built-in tools in the next round"
                            )
                    else:  # Renew the conversation
                        (
                            working_status,
                            working_messages,
                            available_tools,
                            system_tools,
                            custom_tools,
                            built_in_tools,
                            tool_switch,
                            function_call_enabled,
                        ) = self._get_curr_messages_and_tools(task)
                else:
                    # No function calls - check if we should continue or stop
                    if self.state.status == "voted":
                        # Agent has voted, exit the work loop
                        break
                    else:
                        # Check if there is any update from other agents that are unseen by this agent
                        if has_update and working_status != "initial":
                            # Renew the conversation within the loop
                            (
                                working_status,
                                working_messages,
                                available_tools,
                                system_tools,
                                custom_tools,
                                built_in_tools,
                                tool_switch,
                                function_call_enabled,
                            ) = self._get_curr_messages_and_tools(task)
                        else:  # Continue the current conversation and prompting checkin
                            working_messages.append(
                                {
                                    "role": "user",
                                    "content": "Finish your work above by making a tool call of `vote` or `add_answer`. Make sure you actually call the tool.",
                                }
                            )

                    # Switch to custom tools in the next round
                    if tool_switch:
                        available_tools = system_tools + custom_tools
                        function_call_enabled = True
                        print(
                            f"🔄 Agent {self.agent_id} (Gemini) switching to custom tools in the next round"
                        )

                curr_round += 1
                self.state.chat_round += 1

                # Check if agent voted or failed
                if self.state.status in ["voted", "failed"]:
                    break

            except Exception as e:
                print(
                    f"❌ Agent {self.agent_id} error in round {self.state.chat_round}: {e}"
                )
                if self.orchestrator:
                    self.orchestrator.mark_agent_failed(self.agent_id, str(e))

                self.state.chat_round += 1
                curr_round += 1
                break

        return working_messages


def create_agent(
    agent_type: str,
    agent_id: int,
    orchestrator=None,
    model_config: Optional[ModelConfig] = None,
    **kwargs,
) -> MassAgent:
    """
    Factory function to create agents of different types.

    Args:
        agent_type: Type of agent ("openai", "gemini", "grok")
        agent_id: Unique identifier for the agent
        orchestrator: Reference to the MassOrchestrator
        model_config: Model configuration
        **kwargs: Additional arguments

    Returns:
        MassAgent instance of the specified type
    """
    agent_classes = {
        "openai": OpenAIMassAgent,
        "gemini": GeminiMassAgent,
        "grok": GrokMassAgent,
    }

    if agent_type not in agent_classes:
        raise ValueError(
            f"Unknown agent type: {agent_type}. Available types: {list(agent_classes.keys())}"
        )

    return agent_classes[agent_type](
        agent_id=agent_id,
        orchestrator=orchestrator,
        model_config=model_config,
        **kwargs,
    )
