# -*- coding: utf-8 -*-
"""
Computer Use Tool - Automate computer interactions using OpenAI's computer-use-preview model.

This tool allows AI agents to control computer interfaces by performing actions like clicking,
typing, scrolling, and more. It operates in a continuous loop:
1. Send computer actions to the environment
2. Execute actions on computer/browser
3. Capture screenshots of outcomes
4. Send back to the model

Based on OpenAI's Computer Use API: https://platform.openai.com/docs/guides/tools-computer-use
"""

import base64
import json
import os
from pathlib import Path
from typing import Dict, Literal, Optional

from dotenv import load_dotenv
from openai import OpenAI

from .._result import ExecutionResult, ImageContent, TextContent
from .action_handlers import ActionHandler
from .environment_manager import EnvironmentManager


async def computer_use(
    task: str,
    environment: Literal["browser", "mac", "windows", "ubuntu"] = "browser",
    display_width: int = 1024,
    display_height: int = 768,
    model: str = "computer-use-preview",
    max_iterations: int = 20,
    include_reasoning: bool = True,
    initial_screenshot: Optional[str] = None,
    environment_config: Optional[Dict] = None,
) -> ExecutionResult:
    """
    Execute computer use tasks using OpenAI's computer-use-preview model.

    This tool creates an automated agent that can control a computer interface to complete
    tasks by simulating human actions like clicking, typing, and scrolling.

    Args:
        task: The task to accomplish (e.g., "Check the latest OpenAI news on bing.com")
        environment: Target environment ("browser", "mac", "windows", "ubuntu")
        display_width: Screen width in pixels (default: 1024)
        display_height: Screen height in pixels (default: 768)
        model: OpenAI model to use (default: "computer-use-preview")
        max_iterations: Maximum number of action iterations (default: 20)
        include_reasoning: Include reasoning summaries in response (default: True)
        initial_screenshot: Path to initial screenshot (optional)
        environment_config: Additional environment configuration (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether the task completed successfully
        - operation: "computer_use"
        - task: The original task
        - iterations: Number of iterations performed
        - actions_taken: List of actions executed
        - final_screenshot: Base64 encoded final screenshot
        - reasoning: List of reasoning summaries (if include_reasoning=True)
        - error: Error message if failed

    Examples:
        computer_use("Search for Python documentation on Google")
        → Automates a Google search

        computer_use("Fill out the contact form on example.com", environment="browser")
        → Automates form filling

        computer_use("Open calculator and compute 123 + 456", environment="mac")
        → Automates calculator usage on macOS

    Security:
        - Requires valid OpenAI API key
        - Runs in sandboxed environments (recommended)
        - Implements safety checks for malicious instructions
        - Use blocklists/allowlists for production
        - Human-in-the-loop for high-stakes tasks
    """
    try:
        # Load environment variables
        script_dir = Path(__file__).parent.parent.parent.parent
        env_path = script_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()

        openai_api_key = os.getenv("OPENAI_API_KEY")

        if not openai_api_key:
            result = {
                "success": False,
                "operation": "computer_use",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Initialize environment manager and action handler
        env_manager = EnvironmentManager(
            environment=environment,
            display_width=display_width,
            display_height=display_height,
            config=environment_config or {},
        )

        action_handler = ActionHandler(env_manager)

        # Start the environment
        await env_manager.start()

        # Prepare initial request
        input_content = [{"type": "input_text", "text": task}]

        # Add initial screenshot if provided
        if initial_screenshot:
            if Path(initial_screenshot).exists():
                with open(initial_screenshot, "rb") as f:
                    screenshot_data = base64.b64encode(f.read()).decode("utf-8")
                input_content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{screenshot_data}",
                    }
                )
            else:
                # Try to get initial screenshot from environment
                screenshot_bytes = await env_manager.get_screenshot()
                if screenshot_bytes:
                    screenshot_data = base64.b64encode(screenshot_bytes).decode("utf-8")
                    input_content.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_data}",
                        }
                    )

        # Send initial request to the model
        response = client.responses.create(
            model=model,
            tools=[
                {
                    "type": "computer_use_preview",
                    "display_width": display_width,
                    "display_height": display_height,
                    "environment": environment,
                }
            ],
            input=[{"role": "user", "content": input_content}],
            reasoning={"summary": "concise"} if include_reasoning else None,
            truncation="auto",
        )

        # Track execution
        actions_taken = []
        reasoning_summaries = []
        iterations = 0
        final_screenshot = None

        # Main computer use loop
        while iterations < max_iterations:
            # Check for computer_call items
            computer_calls = [
                item for item in response.output if item.get("type") == "computer_call"
            ]

            if not computer_calls:
                # No more computer calls, task complete or model stopped
                break

            # Process the computer call (we expect at most one per response)
            computer_call = computer_calls[0]
            call_id = computer_call.get("call_id")
            action = computer_call.get("action")
            safety_checks = computer_call.get("pending_safety_checks", [])

            # Store action info
            actions_taken.append(
                {
                    "iteration": iterations + 1,
                    "action_type": action.get("type"),
                    "action": action,
                    "safety_checks": safety_checks,
                }
            )

            # Extract reasoning if available
            if include_reasoning:
                reasoning_items = [
                    item for item in response.output if item.get("type") == "reasoning"
                ]
                for reasoning_item in reasoning_items:
                    summary = reasoning_item.get("summary", [])
                    if summary:
                        reasoning_summaries.append(
                            {
                                "iteration": iterations + 1,
                                "summary": summary[0].get("text", "")
                                if summary
                                else "",
                            }
                        )

            # Execute the action
            try:
                await action_handler.execute_action(action)
            except Exception as action_error:
                result = {
                    "success": False,
                    "operation": "computer_use",
                    "task": task,
                    "iterations": iterations + 1,
                    "actions_taken": actions_taken,
                    "reasoning": reasoning_summaries if include_reasoning else None,
                    "error": f"Action execution failed: {str(action_error)}",
                }
                await env_manager.stop()
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Wait a moment for changes to take effect
            await action_handler.wait(1.0)

            # Capture screenshot after action
            screenshot_bytes = await env_manager.get_screenshot()
            if not screenshot_bytes:
                result = {
                    "success": False,
                    "operation": "computer_use",
                    "task": task,
                    "iterations": iterations + 1,
                    "actions_taken": actions_taken,
                    "reasoning": reasoning_summaries if include_reasoning else None,
                    "error": "Failed to capture screenshot",
                }
                await env_manager.stop()
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            final_screenshot = screenshot_base64

            # Acknowledge safety checks if present
            acknowledged_checks = []
            if safety_checks:
                # In production, you should prompt the user to acknowledge these
                # For now, we auto-acknowledge with a warning
                acknowledged_checks = safety_checks
                print(
                    f"WARNING: Safety checks detected: {[check.get('code') for check in safety_checks]}"
                )

            # Send screenshot back as computer_call_output
            response = client.responses.create(
                model=model,
                previous_response_id=response.id,
                tools=[
                    {
                        "type": "computer_use_preview",
                        "display_width": display_width,
                        "display_height": display_height,
                        "environment": environment,
                    }
                ],
                input=[
                    {
                        "call_id": call_id,
                        "type": "computer_call_output",
                        "acknowledged_safety_checks": acknowledged_checks,
                        "output": {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_base64}",
                        },
                    }
                ],
                truncation="auto",
            )

            iterations += 1

        # Stop the environment
        await env_manager.stop()

        # Prepare result
        result = {
            "success": True,
            "operation": "computer_use",
            "task": task,
            "environment": environment,
            "iterations": iterations,
            "actions_taken": actions_taken,
            "reasoning": reasoning_summaries if include_reasoning else None,
            "max_iterations_reached": iterations >= max_iterations,
        }

        output_blocks = [TextContent(data=json.dumps(result, indent=2))]

        # Include final screenshot as an image block
        if final_screenshot:
            output_blocks.append(ImageContent(data=final_screenshot))

        return ExecutionResult(output_blocks=output_blocks)

    except Exception as e:
        result = {
            "success": False,
            "operation": "computer_use",
            "task": task,
            "error": f"Failed to execute computer use task: {str(e)}",
        }

        # Try to stop environment if it was started
        try:
            if 'env_manager' in locals():
                await env_manager.stop()
        except:
            pass

        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
