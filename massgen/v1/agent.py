import os
import sys
import time
import json
from typing import Callable, Union, Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from dotenv import load_dotenv

load_dotenv()

from .types import TaskInput, AgentState, AgentResponse, ModelConfig
from .utils import get_agent_type_from_model, function_to_json
from abc import ABC, abstractmethod
from typing import Any, Callable, Union, Optional, List, Dict
from .backends import oai, gemini, grok

# TASK_INSTRUCTION = """
# Please use your expertise and tools (if available) to fully verify if the best CURRENT ANSWER addresses the ORIGINAL MESSAGE.
# - If YES, use the `vote` tool to record your vote and skip the `add_answer` tool.
# - If NO, do additional work first, then use the `add_answer` tool to record a better answer to the ORIGINAL MESSAGE. Make sure you actually call the tool.

# Any answer must be self-contained, complete, well-sourced, compelling, and ready to serve as the definitive final response.
# """

SYSTEM_INSTRUCTION = f"""
You are evaluating answers from multiple agents for final response to a message. 

For every aspect, claim, reasoning steps in the CURRENT ANSWERS, verify correctness, factual accuracy, and completeness using your expertise, reasoning, and available tools.

If the CURRENT ANSWERS fully address the ORIGINAL MESSAGE, use the `vote` tool to record your vote and skip the `add_answer` tool.

If the CURRENT ANSWERS are incomplete, incorrect, or not fully address the ORIGINAL MESSAGE, conduct any necessary reasoning or research. Then, use the `add_answer` tool to submit a new response.

Your new answer must be self-contained, process-complete, well-sourced, and compelling—ready to serve as the final reply.

**Important**: Be sure to actually call the `add_answer` tool to submit your new answer.

*Note*: The CURRENT TIME is **{time.strftime("%Y-%m-%d %H:%M:%S")}**.
For any time-sensitive requests, use the search tool (if available) rather than relying on prior knowledge.
"""

AGENT_ANSWER_MESSAGE = """
<ORIGINAL MESSAGE>
{task}
<END OF ORIGINAL MESSAGE>

<CURRENT ANSWERS>
{agent_answers}
<END OF CURRENT ANSWERS>
"""

AGENT_ANSWER_AND_VOTE_MESSAGE = """
<ORIGINAL MESSAGE>
{task}
<END OF ORIGINAL MESSAGE>

<CURRENT ANSWERS>
{agent_answers}
<END OF CURRENT ANSWERS>

<CURRENT VOTES>
{agent_votes}
<END OF CURRENT VOTES>
"""


class MassAgent(ABC):
    """
    Abstract base class for all agents in the MassGen system.

    All agent implementations must inherit from this class and implement
    the required methods while following the standardized workflow.
    """

    def __init__(
        self,
        agent_id: int,
        orchestrator=None,
        model_config: Optional[ModelConfig] = None,
        stream_callback: Optional[Callable] = None,
        **kwargs,
    ):
        """
        Initialize the agent with configuration parameters.

        Args:
            agent_id: Unique identifier for this agent
            orchestrator: Reference to the MassOrchestrator
            model_config: Configuration object containing model parameters (model, tools,
                         temperature, top_p, max_tokens, inference_timeout, max_retries, stream)
            stream_callback: Optional callback function for streaming chunks
            agent_type: Type of agent ("openai", "gemini", "grok") to determine backend
            **kwargs: Additional parameters specific to the agent implementation
        """
        self.agent_id = agent_id
        self.orchestrator = orchestrator
        self.state = AgentState(agent_id=agent_id)

        # Initialize model configuration with defaults if not provided
        if model_config is None:
            model_config = ModelConfig()

        # Store configuration parameters
        self.model = model_config.model
        self.agent_type = get_agent_type_from_model(self.model)
        # Map agent types to their backend modules
        process_message_impl_map = {
            "openai": oai.process_message,
            "gemini": gemini.process_message,
            "grok": grok.process_message,
        }
        if self.agent_type not in process_message_impl_map:
            raise ValueError(
                f"Unknown agent type: {self.agent_type}. Available types: {list(process_message_impl_map.keys())}"
            )

        # Get the appropriate process_message implementation based on the agent type
        self.process_message_impl = process_message_impl_map[self.agent_type]

        # Other model configuration parameters
        self.tools = model_config.tools
        self.max_retries = model_config.max_retries
        self.max_rounds = model_config.max_rounds
        self.max_tokens = model_config.max_tokens
        self.temperature = model_config.temperature
        self.top_p = model_config.top_p
        self.inference_timeout = model_config.inference_timeout
        self.stream = model_config.stream
        self.stream_callback = stream_callback
        self.kwargs = kwargs

    def process_message(
        self, messages: List[Dict[str, str]], tools: List[str] = None
    ) -> AgentResponse:
        """
        Core LLM inference function for task processing.

        This method handles the actual LLM interaction using the agent's
        specific backend (OpenAI, Gemini, Grok, etc.) and returns a standardized response.
        All configuration parameters are stored as instance variables and accessed
        via self.model, self.tools, self.temperature, etc.

        Args:
            messages: List of messages in OpenAI format
            tools: List of tools to use

        Returns:
            AgentResponse containing the agent's response text, code, citations, etc.
        """

        # Create configuration dictionary using model configuration parameters
        config = {
            "model": self.model,
            "max_retries": self.max_retries,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "api_key": None,  # Let backend use environment variable
            "stream": self.stream,
            "stream_callback": self.stream_callback,
        }

        try:
            # Use ThreadPoolExecutor to implement timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.process_message_impl, messages=messages, tools=tools, **config
                )

                try:
                    # Wait for result with timeout
                    result = future.result(timeout=self.inference_timeout)
                    # Backend implementations now return AgentResponse objects directly
                    return result
                except FutureTimeoutError:
                    # Mark agent as failed due to timeout
                    timeout_msg = f"Agent {self.agent_id} timed out after {self.inference_timeout} seconds"
                    self.mark_failed(timeout_msg)
                    return AgentResponse(
                        text=f"Agent processing timed out after {self.inference_timeout} seconds",
                        code=[],
                        citations=[],
                        function_calls=[],
                    )

        except Exception as e:
            # Return error response
            return AgentResponse(
                text=f"Error in {self.model} agent processing: {str(e)}",
                code=[],
                citations=[],
                function_calls=[],
            )

    def add_answer(self, new_answer: str):
        """
        Record your work on the task: your analysis, approach, solution, and reasoning. Update when you solve the problem, find better solutions, or incorporate valuable insights from other agents.

        Args:
            answer: The new answer, which should be self-contained, complete, and ready to serve as the definitive final response.
        """
        # Use the orchestrator to update the answer and notify other agents to restart
        self.orchestrator.notify_answer_update(self.agent_id, new_answer)
        return f"The new answer has been added."

    def vote(
        self, agent_id: int, reason: str = "", invalid_vote_options: List[int] = []
    ):
        """
        Vote for the representative agent, who you believe has found the correct solution.

        Args:
            agent_id: ID of the voted agent
            reason: Your full explanation of why you voted for this agent
            invalid_vote_options: The list of agent IDs that are invalid to vote for (have new updates)
        """
        if agent_id in invalid_vote_options:
            return f"Error: Voting for agent {agent_id} is not allowed as its answer has been updated!"
        self.orchestrator.cast_vote(self.agent_id, agent_id, reason)
        return f"Your vote for Agent {agent_id} has been cast."

    def check_update(self) -> List[int]:
        """
        Check if there are any updates from other agents since this agent last saw them.
        """
        agents_with_update = set()
        # Get updates from other agents since this agent last saw them
        for other_id, other_state in self.orchestrator.agent_states.items():
            if other_id != self.agent_id and other_state.updated_answers:
                for update in other_state.updated_answers:
                    last_seen = self.state.seen_updates_timestamps.get(other_id, 0)
                    # Check if the update is newer than the last seen timestamp
                    if update.timestamp > last_seen:
                        # update the last seen timestamp
                        self.state.seen_updates_timestamps[other_id] = update.timestamp
                        agents_with_update.add(other_id)
        return list(agents_with_update)

    def mark_failed(self, reason: str = ""):
        """
        Mark this agent as failed.

        Args:
            reason: Optional reason for the failure
        """
        # Report the failure to the orchestrator for logging
        self.orchestrator.mark_agent_failed(self.agent_id, reason)

    def deduplicate_function_calls(self, function_calls: List[Dict]):
        """Deduplicate function calls by their name and arguments."""
        deduplicated_function_calls = []
        for func_call in function_calls:
            if func_call not in deduplicated_function_calls:
                deduplicated_function_calls.append(func_call)
        return deduplicated_function_calls

    def _execute_function_calls(
        self, function_calls: List[Dict], invalid_vote_options: List[int] = []
    ):
        """Execute function calls and return function outputs."""
        from .tools import register_tool

        function_outputs = []
        successful_called = []

        for func_call in function_calls:
            func_call_id = func_call.get("call_id")
            func_name = func_call.get("name")
            func_args = func_call.get("arguments", {})
            if isinstance(func_args, str):
                func_args = json.loads(func_args)

            try:
                if func_name == "add_answer":
                    result = self.add_answer(func_args.get("new_answer", ""))
                elif func_name == "vote":
                    result = self.vote(
                        func_args.get("agent_id"),
                        func_args.get("reason", ""),
                        invalid_vote_options,
                    )
                elif func_name in register_tool:
                    result = register_tool[func_name](**func_args)
                else:
                    result = {
                        "type": "function_call_output",
                        "call_id": func_call_id,
                        "output": f"Error: Function '{func_name}' not found in tool mapping",
                    }

                # Add function call and result to messages
                function_output = {
                    "type": "function_call_output",
                    "call_id": func_call_id,
                    "output": str(result),
                }
                function_outputs.append(function_output)
                successful_called.append(True)

            except Exception as e:
                # Handle execution errors
                error_output = {
                    "type": "function_call_output",
                    "call_id": func_call_id,
                    "output": f"Error executing function: {str(e)}",
                }
                function_outputs.append(error_output)
                successful_called.append(False)
                print(f"Error executing function {func_name}: {e}")

                # DEBUGGING
                with open("function_calls.txt", "a") as f:
                    f.write(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Agent {self.agent_id} ({self.model}):\n"
                    )
                    f.write(f"{json.dumps(error_output, indent=2)}\n")
                    f.write(f"Successful called: {False}\n")

        return function_outputs, successful_called

    def _get_system_tools(self) -> List[Dict[str, Any]]:
        """
        The system tools available to this agent for orchestration:
        - add_answer: Your added new answer, which should be self-contained, complete, and ready to serve as the definitive final response.
        - vote: Vote for the representative agent, who you believe has found the correct solution.
        """
        add_answer_schema = {
            "type": "function",
            "name": "add_answer",
            "description": "Add your new answer if you believe it is better than the current answers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_answer": {
                        "type": "string",
                        "description": "Your new answer, which should be self-contained, complete, and ready to serve as the definitive final response.",
                    }
                },
                "required": ["new_answer"],
            },
        }
        vote_schema = {
            "type": "function",
            "name": "vote",
            "description": "Vote for the best agent to present final answer. Submit its agent_id (integer) and reason for your vote.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "integer",
                        "description": "The ID of the agent you believe has found the best answer that addresses the original message.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Your full explanation of why you voted for this agent.",
                    },
                },
                "required": ["agent_id", "reason"],
            },
        }
        # Check if there are any available options to vote for. If not, only return the add_answer schema.
        available_options = [
            agent_id
            for agent_id, agent_state in self.orchestrator.agent_states.items()
            if agent_state.curr_answer
        ]
        return (
            [add_answer_schema, vote_schema]
            if available_options
            else [add_answer_schema]
        )

    def _get_registered_tools(self) -> List[Dict[str, Any]]:
        """Return the tool schema for the tools that are available to this agent."""
        # Register tools from the global registry, JSON schema
        custom_tools = []
        from .tools import register_tool

        for tool_name, tool_func in register_tool.items():
            if tool_name in self.tools:
                tool_schema = function_to_json(tool_func)
                custom_tools.append(tool_schema)
        return custom_tools

    def _get_builtin_tools(self) -> List[Dict[str, Any]]:
        """
        Override the parent method due to the Gemini's limitation.
        Return the built-in tools that are available to Gemini models.
        live_search and code_execution are supported right now.
        However, the built-in tools and function call are not supported at the same time.
        """
        builtin_tools = []
        for tool in self.tools:
            if tool in ["live_search", "code_execution"]:
                builtin_tools.append(tool)
        return builtin_tools

    def _get_all_answers(self) -> List[str]:
        """Get all answers from all agents.
        Format:
        **Agent 1**: Answer 1
        **Agent 2**: Answer 2
        ...
        """
        # Case 1: Initial round without running answer
        agent_answers = []
        for agent_id, agent_state in self.orchestrator.agent_states.items():
            if agent_state.curr_answer:
                agent_answers.append(f"**Agent {agent_id}**: {agent_state.curr_answer}")
        return agent_answers

    def _get_all_votes(self) -> List[str]:
        """Get all votes from all agents.
        Format:
        **Vote for Agent 1**: Reason 1
        **Vote for Agent 2**: Reason 2
        ...
        """
        agent_votes = []
        for agent_id, agent_state in self.orchestrator.agent_states.items():
            if agent_state.curr_vote:
                agent_votes.append(
                    f"**Vote for Agent {agent_state.curr_vote.target_id}**: {agent_state.curr_vote.reason}"
                )
        return agent_votes

    def _get_task_input(self, task: TaskInput) -> str:
        """Get the initial task input as the user message. Return Both the current status and the task input."""
        # Case 1: Initial round without running answer
        if not self.state.curr_answer:
            status = "initial"
            task_input = (
                AGENT_ANSWER_MESSAGE.format(task=task.question, agent_answers="None")
                + "There are no current answers right now. Please use your expertise and tools (if available) to provide a new answer and submit it using the `add_answer` tool first."
            )
            return status, task_input

        # Not the initial round
        all_agent_answers = self._get_all_answers()
        all_agent_answers_str = "\n\n".join(all_agent_answers)
        # Check if in debate mode or not
        voted_agents = [
            agent_id
            for agent_id, agent_state in self.orchestrator.agent_states.items()
            if agent_state.curr_vote is not None
        ]
        if len(voted_agents) == len(self.orchestrator.agent_states):
            # Case 2: All agents have voted and are debating. Can not use agent status to check as they have been updated to 'working/debate'
            all_agent_votes = self._get_all_votes()
            all_agent_votes_str = "\n\n".join(all_agent_votes)
            status = "debate"
            task_input = AGENT_ANSWER_AND_VOTE_MESSAGE.format(
                task=task.question,
                agent_answers=all_agent_answers_str,
                agent_votes=all_agent_votes_str,
            )
        else:
            # Case 3: All agents are working and not in debating
            status = "working"
            task_input = AGENT_ANSWER_MESSAGE.format(
                task=task.question, agent_answers=all_agent_answers_str
            )

        return status, task_input

    def _get_task_input_messages(self, user_input: str) -> List[Dict[str, str]]:
        """Get the task input messages for the agent."""
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_input},
        ]

    def _get_curr_messages_and_tools(self, task: TaskInput):
        """Get the current messages and tools for the agent."""
        working_status, user_input = self._get_task_input(task)
        working_messages = self._get_task_input_messages(user_input)
        # Get available tools (system tools + built-in tools + custom tools)
        all_tools = []
        all_tools.extend(self._get_builtin_tools())
        all_tools.extend(self._get_registered_tools())
        all_tools.extend(self._get_system_tools())
        return working_status, working_messages, all_tools

    def work_on_task(self, task: TaskInput) -> List[Dict[str, str]]:
        """
        Work on the task with conversation continuation.

        Args:
            task: The task to work on
            messages: Current conversation history
            restart_instruction: Optional instruction for restarting work (e.g., updates from other agents)

        Returns:
            Updated conversation history including agent's work

        This method should be implemented by concrete agent classes.
        The agent continues the conversation until it votes or reaches max rounds.
        """

        # Initialize working messages
        curr_round = 0
        working_status, working_messages, all_tools = self._get_curr_messages_and_tools(
            task
        )

        # Start the task solving loop
        while curr_round < self.max_rounds and self.state.status == "working":
            try:
                # Call LLM with current conversation
                result = self.process_message(
                    messages=working_messages, tools=all_tools
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
                    # Not voting if there is any update
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

                    if (
                        not renew_conversation
                    ):  # Add all function call results to the current conversation and continue the loop
                        for function_call, function_output in zip(
                            result.function_calls, function_outputs
                        ):
                            working_messages.extend([function_call, function_output])
                    else:  # Renew the conversation
                        working_status, working_messages, all_tools = (
                            self._get_curr_messages_and_tools(task)
                        )
                else:
                    # No function calls - check if we should continue or stop
                    if self.state.status == "voted":
                        # Agent has voted, exit the work loop
                        break
                    else:
                        # Check if there is any update from other agents that are unseen by this agent
                        if has_update and working_status != "initial":
                            # The vote option has changed, thus we need to renew the conversation within the loop
                            working_status, working_messages, all_tools = (
                                self._get_curr_messages_and_tools(task)
                            )
                        else:  # Continue the current conversation and prompting checkin
                            working_messages.append(
                                {
                                    "role": "user",
                                    "content": "Finish your work above by making a tool call of `vote` or `add_answer`. Make sure you actually call the tool.",
                                }
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
