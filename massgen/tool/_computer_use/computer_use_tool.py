# -*- coding: utf-8 -*-
"""
Computer use tool for automating browser and computer interactions using OpenAI's computer-use-preview model.

This tool implements the Computer Using Agent (CUA) loop that allows the model to control a computer
or browser environment by sending actions (click, type, scroll, etc.) and receiving screenshots.
"""

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI

from massgen.logger_config import logger
from massgen.tool._result import ExecutionResult, TextContent

# Optional dependencies with graceful fallback
try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None

try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None


class ComputerUseError(Exception):
    """Base exception for computer use tool errors."""


class EnvironmentNotSupportedError(ComputerUseError):
    """Raised when an environment is not supported."""


class ActionExecutionError(ComputerUseError):
    """Raised when an action fails to execute."""


def get_screenshot_browser(page: Any) -> bytes:
    """
    Take a screenshot using Playwright browser.

    Args:
        page: Playwright page instance

    Returns:
        Screenshot bytes
    """
    return page.screenshot()


def get_screenshot_docker(container: Any, display: str = ":99") -> bytes:
    """
    Take a screenshot from Docker container using scrot.

    Args:
        container: Docker container instance
        display: X11 display number

    Returns:
        Screenshot bytes
    """
    import io

    # Use scrot to capture screenshot
    result = container.exec_run(f"scrot -o /tmp/screenshot.png", environment={"DISPLAY": display})

    if result.exit_code != 0:
        raise ActionExecutionError(f"Failed to capture screenshot: {result.output.decode()}")

    # Read the screenshot file
    bits, stat = container.get_archive("/tmp/screenshot.png")
    file_obj = io.BytesIO()
    for chunk in bits:
        file_obj.write(chunk)
    file_obj.seek(0)

    # Extract from tar archive
    import tarfile

    tar = tarfile.open(fileobj=file_obj)
    screenshot_file = tar.extractfile("screenshot.png")
    screenshot_bytes = screenshot_file.read()

    return screenshot_bytes


def execute_browser_action(page: Any, action: Dict[str, Any]) -> None:
    """
    Execute a computer action on Playwright browser page.

    Args:
        page: Playwright page instance
        action: Action dictionary from model response

    Raises:
        ActionExecutionError: If action execution fails
    """
    action_type = action.get("type")

    try:
        if action_type == "click":
            x, y = action.get("x", 0), action.get("y", 0)
            button = action.get("button", "left")
            logger.info(f"Action: click at ({x}, {y}) with button '{button}'")
            if button not in ["left", "right", "middle"]:
                button = "left"
            page.mouse.click(x, y, button=button)

        elif action_type == "double_click":
            x, y = action.get("x", 0), action.get("y", 0)
            logger.info(f"Action: double_click at ({x}, {y})")
            page.mouse.dblclick(x, y)

        elif action_type == "scroll":
            x, y = action.get("x", 0), action.get("y", 0)
            scroll_x = action.get("scroll_x", 0)
            scroll_y = action.get("scroll_y", 0)
            logger.info(f"Action: scroll at ({x}, {y}) with offsets (scroll_x={scroll_x}, scroll_y={scroll_y})")
            page.mouse.move(x, y)
            page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")

        elif action_type == "keypress" or action_type == "key":
            keys = action.get("keys", [])
            if isinstance(keys, str):
                keys = [keys]
            for k in keys:
                logger.info(f"Action: keypress '{k}'")
                # Map common keys
                key_mapping = {
                    "enter": "Enter",
                    "return": "Enter",
                    "space": " ",
                    "tab": "Tab",
                    "backspace": "Backspace",
                    "delete": "Delete",
                    "escape": "Escape",
                    "esc": "Escape",
                }
                key_to_press = key_mapping.get(k.lower(), k)
                page.keyboard.press(key_to_press)

        elif action_type == "type":
            text = action.get("text", "")
            logger.info(f"Action: type text: {text}")
            page.keyboard.type(text, delay=50)  # Add slight delay for more human-like typing

        elif action_type == "wait":
            wait_time = action.get("duration", 2)
            logger.info(f"Action: wait for {wait_time} seconds")
            time.sleep(wait_time)

        elif action_type == "screenshot":
            logger.info("Action: screenshot (will be captured automatically)")
            # Screenshot is taken at each loop iteration

        else:
            logger.warning(f"Unknown action type: {action_type}")

    except Exception as e:
        raise ActionExecutionError(f"Failed to execute action {action_type}: {str(e)}")


def execute_docker_action(container: Any, action: Dict[str, Any], display: str = ":99") -> None:
    """
    Execute a computer action on Docker container using xdotool.

    Args:
        container: Docker container instance
        action: Action dictionary from model response
        display: X11 display number

    Raises:
        ActionExecutionError: If action execution fails
    """
    action_type = action.get("type")

    try:
        env = {"DISPLAY": display}

        if action_type == "click":
            x, y = action.get("x", 0), action.get("y", 0)
            button = action.get("button", "left")
            logger.info(f"Action: click at ({x}, {y}) with button '{button}'")

            # Map button to xdotool button number
            button_map = {"left": "1", "middle": "2", "right": "3"}
            button_num = button_map.get(button, "1")

            # Move mouse and click
            container.exec_run(f"xdotool mousemove {x} {y}", environment=env)
            time.sleep(0.1)
            container.exec_run(f"xdotool click {button_num}", environment=env)

        elif action_type == "double_click":
            x, y = action.get("x", 0), action.get("y", 0)
            logger.info(f"Action: double_click at ({x}, {y})")
            container.exec_run(f"xdotool mousemove {x} {y}", environment=env)
            time.sleep(0.1)
            container.exec_run("xdotool click --repeat 2 1", environment=env)

        elif action_type == "scroll":
            x, y = action.get("x", 0), action.get("y", 0)
            scroll_x = action.get("scroll_x", 0)
            scroll_y = action.get("scroll_y", 0)
            logger.info(f"Action: scroll at ({x}, {y}) with offsets (scroll_x={scroll_x}, scroll_y={scroll_y})")

            # Move to position
            container.exec_run(f"xdotool mousemove {x} {y}", environment=env)
            time.sleep(0.1)

            # Scroll (xdotool uses button 4 for up, 5 for down)
            if scroll_y < 0:  # Scroll up
                clicks = abs(scroll_y) // 10
                for _ in range(clicks):
                    container.exec_run("xdotool click 4", environment=env)
            elif scroll_y > 0:  # Scroll down
                clicks = scroll_y // 10
                for _ in range(clicks):
                    container.exec_run("xdotool click 5", environment=env)

        elif action_type == "keypress" or action_type == "key":
            keys = action.get("keys", [])
            if isinstance(keys, str):
                keys = [keys]
            for k in keys:
                logger.info(f"Action: keypress '{k}'")
                # xdotool key names
                key_mapping = {
                    "enter": "Return",
                    "space": "space",
                    "tab": "Tab",
                    "backspace": "BackSpace",
                    "delete": "Delete",
                    "escape": "Escape",
                    "esc": "Escape",
                }
                key_to_press = key_mapping.get(k.lower(), k)
                container.exec_run(f"xdotool key {key_to_press}", environment=env)

        elif action_type == "type":
            text = action.get("text", "")
            logger.info(f"Action: type text: {text}")
            # Escape special characters for shell
            escaped_text = text.replace("'", "'\\''")
            container.exec_run(f"xdotool type '{escaped_text}'", environment=env)

        elif action_type == "wait":
            wait_time = action.get("duration", 2)
            logger.info(f"Action: wait for {wait_time} seconds")
            time.sleep(wait_time)

        elif action_type == "screenshot":
            logger.info("Action: screenshot (will be captured automatically)")

        else:
            logger.warning(f"Unknown action type: {action_type}")

    except Exception as e:
        raise ActionExecutionError(f"Failed to execute Docker action {action_type}: {str(e)}")


def run_computer_use_loop(
    client: OpenAI,
    initial_response: Any,
    environment_type: str,
    environment_instance: Any,
    display_width: int,
    display_height: int,
    max_iterations: int = 50,
    environment_config: Optional[Dict[str, Any]] = None,
    model: str = "computer-use-preview",
) -> Dict[str, Any]:
    """
    Run the computer use loop that executes actions and sends screenshots back to the model.

    Args:
        client: OpenAI client instance
        initial_response: Initial response from the model
        environment_type: Type of environment ("browser", "docker", etc.)
        environment_instance: Browser page or Docker container instance
        display_width: Display width in pixels
        display_height: Display height in pixels
        max_iterations: Maximum number of iterations to prevent infinite loops
        environment_config: Additional environment-specific configuration
        model: Model to use for computer control (default: "computer-use-preview")

    Returns:
        Dictionary with execution results and logs
    """
    response = initial_response
    iteration_count = 0
    action_log = []
    environment_config = environment_config or {}

    while iteration_count < max_iterations:
        iteration_count += 1
        logger.info(f"Computer use loop iteration {iteration_count}/{max_iterations}")

        # Check if there are any computer_call items
        computer_calls = [item for item in response.output if getattr(item, "type", None) == "computer_call"]

        if not computer_calls:
            logger.info("No computer call found. Task completed.")
            # Extract final text output if available
            text_outputs = [str(item) for item in response.output if getattr(item, "type", None) != "computer_call"]
            action_log.append({"iteration": iteration_count, "status": "completed", "output": text_outputs})
            break

        # Process the computer call
        computer_call = computer_calls[0]
        call_id = computer_call.call_id
        action = computer_call.action
        action_dict = {
            "type": action.type,
            "x": getattr(action, "x", None),
            "y": getattr(action, "y", None),
            "button": getattr(action, "button", None),
            "scroll_x": getattr(action, "scroll_x", None),
            "scroll_y": getattr(action, "scroll_y", None),
            "keys": getattr(action, "keys", None),
            "text": getattr(action, "text", None),
            "duration": getattr(action, "duration", None),
        }

        # Log the action
        action_log.append({"iteration": iteration_count, "action": action_dict, "call_id": call_id})

        # Check for pending safety checks
        pending_checks = getattr(computer_call, "pending_safety_checks", [])
        acknowledged_checks = []

        if pending_checks:
            logger.warning(f"Safety checks triggered: {pending_checks}")
            # Auto-acknowledge safety checks (in production, you should prompt the user)
            for check in pending_checks:
                check_dict = {
                    "id": check.id,
                    "code": check.code,
                    "message": check.message,
                }
                acknowledged_checks.append(check_dict)
                logger.info(f"Auto-acknowledging safety check: {check.code}")

        # Execute the action based on environment type
        try:
            if environment_type == "browser":
                execute_browser_action(environment_instance, action_dict)
            elif environment_type in ["linux", "mac", "windows"]:
                display = environment_config.get("display", ":99")
                execute_docker_action(environment_instance, action_dict, display)
            else:
                raise EnvironmentNotSupportedError(f"Environment type not supported: {environment_type}")

            # Wait a bit for the action to take effect
            time.sleep(1)

        except Exception as action_error:
            logger.error(f"Failed to execute action: {action_error}")
            action_log.append({"iteration": iteration_count, "error": str(action_error)})
            # Return error result
            return {
                "success": False,
                "error": f"Action execution failed: {str(action_error)}",
                "action_log": action_log,
                "iterations": iteration_count,
            }

        # Capture screenshot
        try:
            if environment_type == "browser":
                screenshot_bytes = get_screenshot_browser(environment_instance)
            elif environment_type in ["linux", "mac", "windows"]:
                display = environment_config.get("display", ":99")
                screenshot_bytes = get_screenshot_docker(environment_instance, display)
            else:
                raise EnvironmentNotSupportedError(f"Environment type not supported: {environment_type}")

            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        except Exception as screenshot_error:
            logger.error(f"Failed to capture screenshot: {screenshot_error}")
            action_log.append({"iteration": iteration_count, "screenshot_error": str(screenshot_error)})
            # Try to continue without screenshot
            screenshot_base64 = ""

        # Prepare the computer_call_output
        computer_call_output = {
            "call_id": call_id,
            "type": "computer_call_output",
            "output": {"type": "computer_screenshot", "image_url": f"data:image/png;base64,{screenshot_base64}"},
        }

        # Add acknowledged safety checks if any
        if acknowledged_checks:
            computer_call_output["acknowledged_safety_checks"] = acknowledged_checks

        # Get current URL if in browser environment
        if environment_type == "browser":
            try:
                current_url = environment_instance.url
                computer_call_output["current_url"] = current_url
            except Exception:
                pass  # URL not available

        # Send the next request with screenshot
        try:
            response = client.responses.create(
                model=model,
                previous_response_id=response.id,
                tools=[
                    {
                        "type": "computer_use_preview",
                        "display_width": display_width,
                        "display_height": display_height,
                        "environment": environment_type,
                    },
                ],
                input=[computer_call_output],
                truncation="auto",
            )

        except Exception as api_error:
            logger.error(f"API request failed: {api_error}")
            action_log.append({"iteration": iteration_count, "api_error": str(api_error)})
            return {
                "success": False,
                "error": f"API request failed: {str(api_error)}",
                "action_log": action_log,
                "iterations": iteration_count,
            }

    # Check if we hit max iterations
    if iteration_count >= max_iterations:
        logger.warning(f"Reached maximum iterations ({max_iterations})")
        return {
            "success": False,
            "error": f"Reached maximum iterations ({max_iterations})",
            "action_log": action_log,
            "iterations": iteration_count,
        }

    # Return success result
    return {
        "success": True,
        "action_log": action_log,
        "iterations": iteration_count,
        "final_output": [str(item) for item in response.output],
    }


async def computer_use(
    task: str,
    environment: str = "browser",
    display_width: int = 1920,
    display_height: int = 1080,
    max_iterations: int = 50,
    include_reasoning: bool = True,
    initial_screenshot_path: Optional[str] = None,
    environment_config: Optional[Dict[str, Any]] = None,
    agent_cwd: Optional[str] = None,
    model: str = "computer-use-preview",
) -> ExecutionResult:
    """
    Execute a computer automation task using OpenAI's computer-use-preview model.

    This tool implements the Computer Using Agent (CUA) loop that allows the model to:
    - Control a web browser (click, type, scroll, navigate)
    - Automate desktop applications (in Docker/VM environments)
    - Perform multi-step workflows
    - Handle safety checks

    Args:
        task: Description of the task to perform (e.g., "Search for Python docs on Google")
        environment: Environment type - "browser", "linux", "mac", "windows"
                    (default: "browser")
                    Note: "linux" requires Docker container setup
        display_width: Display width in pixels (default: 1920)
        display_height: Display height in pixels (default: 1080)
        max_iterations: Maximum number of action iterations to prevent infinite loops (default: 50)
        include_reasoning: Whether to include reasoning summaries in responses (default: True)
        initial_screenshot_path: Optional path to initial screenshot to include in first request
        environment_config: Additional environment-specific configuration
                          For linux/docker: {"container_name": "...", "display": ":99"}
                          For browser: {"headless": False, "browser_type": "chromium"}
        agent_cwd: Agent's current working directory (automatically injected)
        model: Model to use for computer control (default: "computer-use-preview")
               Can be "computer-use-preview" or "gpt-4.1"

    Returns:
        ExecutionResult containing:
        - success: Whether the task completed successfully
        - operation: "computer_use"
        - task: The task description
        - environment: Environment type used
        - iterations: Number of iterations executed
        - action_log: List of actions performed
        - final_output: Final output from the model (if successful)
        - error: Error message (if failed)

    Examples:
        # Browser automation
        computer_use("Search for 'Python asyncio' on Google and summarize the top result")

        # With custom display size
        computer_use(
            "Navigate to example.com and fill the contact form",
            display_width=1280,
            display_height=800
        )

        # Linux/Docker environment
        computer_use(
            "Open calculator and compute 15 * 23",
            environment="linux",
            environment_config={"container_name": "cua-container", "display": ":99"}
        )

    Prerequisites:
        - OPENAI_API_KEY environment variable must be set
        - For browser: `pip install playwright && playwright install`
        - For linux: Docker must be installed and container must be running

    Security:
        - Runs in sandboxed environments (browser or container)
        - Safety checks are triggered for malicious instructions or sensitive domains
        - All actions are logged for auditing
        - Supports allowlists/blocklists (implement in environment_config)
    """
    environment_config = environment_config or {}

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
            return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Prepare initial request
        input_content = [{"type": "input_text", "text": task}]

        # Add initial screenshot if provided
        if initial_screenshot_path:
            base_dir = Path(agent_cwd) if agent_cwd else Path.cwd()
            screenshot_path = Path(initial_screenshot_path)
            if not screenshot_path.is_absolute():
                screenshot_path = (base_dir / screenshot_path).resolve()

            if screenshot_path.exists():
                with open(screenshot_path, "rb") as f:
                    screenshot_bytes = f.read()
                    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                    input_content.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_base64}",
                        },
                    )
                    logger.info(f"Added initial screenshot: {screenshot_path}")

        # Prepare reasoning config
        reasoning_config = {}
        if include_reasoning:
            reasoning_config = {"summary": "concise"}

        # Initialize environment
        environment_instance = None
        cleanup_func = None

        # Map environment names - OpenAI API accepts: browser, linux, mac, windows
        # We support these but execute linux/mac/windows via Docker
        environment_type_for_execution = environment
        if environment in ["ubuntu", "docker"]:
            # Legacy aliases - map to linux for API compatibility
            environment = "linux"
            environment_type_for_execution = "linux"

        try:
            if environment == "browser":
                # Initialize Playwright browser
                if not PLAYWRIGHT_AVAILABLE:
                    result = {
                        "success": False,
                        "operation": "computer_use",
                        "error": "Playwright not installed. Install with: pip install playwright && playwright install",
                    }
                    return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

                playwright = sync_playwright().start()
                browser_type = environment_config.get("browser_type", "chromium")
                headless = environment_config.get("headless", False)

                if browser_type == "chromium":
                    browser = playwright.chromium.launch(headless=headless)
                elif browser_type == "firefox":
                    browser = playwright.firefox.launch(headless=headless)
                elif browser_type == "webkit":
                    browser = playwright.webkit.launch(headless=headless)
                else:
                    browser = playwright.chromium.launch(headless=headless)

                context = browser.new_context(viewport={"width": display_width, "height": display_height})
                page = context.new_page()
                page.goto("about:blank")

                environment_instance = page
                cleanup_func = lambda: (browser.close(), playwright.stop())

                logger.info(f"Initialized {browser_type} browser ({display_width}x{display_height})")

            elif environment in ["linux", "mac", "windows"]:
                # Initialize Docker container for OS-level automation
                if not DOCKER_AVAILABLE:
                    result = {
                        "success": False,
                        "operation": "computer_use",
                        "error": "Docker SDK not installed. Install with: pip install docker",
                    }
                    return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

                docker_client = docker.from_env()
                container_name = environment_config.get("container_name", "cua-container")

                # Try to get existing container or create new one
                try:
                    container = docker_client.containers.get(container_name)
                    if container.status != "running":
                        container.start()
                        time.sleep(2)  # Wait for container to start
                    logger.info(f"Using existing Docker container: {container_name}")
                except docker.errors.NotFound:
                    result = {
                        "success": False,
                        "operation": "computer_use",
                        "error": f"Docker container not found: {container_name}. Please create and start the container first.",
                    }
                    return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

                environment_instance = container
                cleanup_func = None  # Don't stop the container automatically

                logger.info(f"Initialized Docker container: {container_name}")

            else:
                result = {
                    "success": False,
                    "operation": "computer_use",
                    "error": f"Unsupported environment: {environment}. Use 'browser', 'linux', 'mac', or 'windows'.",
                }
                return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

            # Send initial request to model
            logger.info(f"Sending initial request to {model} model")
            logger.info(f"Task: {task}")

            initial_response = client.responses.create(
                model=model,
                tools=[
                    {
                        "type": "computer_use_preview",
                        "display_width": display_width,
                        "display_height": display_height,
                        "environment": environment,
                    },
                ],
                input=[{"role": "user", "content": input_content}],
                reasoning=reasoning_config if reasoning_config else None,
                truncation="auto",
            )

            # Run the computer use loop
            loop_result = run_computer_use_loop(
                client=client,
                initial_response=initial_response,
                environment_type=environment_type_for_execution,
                environment_instance=environment_instance,
                display_width=display_width,
                display_height=display_height,
                max_iterations=max_iterations,
                environment_config=environment_config,
                model=model,
            )

            # Add task info to result
            loop_result["operation"] = "computer_use"
            loop_result["task"] = task
            loop_result["environment"] = environment

            return ExecutionResult(output_blocks=[TextContent(data=json.dumps(loop_result, indent=2))])

        finally:
            # Cleanup environment
            if cleanup_func:
                try:
                    cleanup_func()
                    logger.info("Cleaned up environment")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup environment: {cleanup_error}")

    except Exception as e:
        logger.error(f"Computer use tool failed: {str(e)}")
        result = {
            "success": False,
            "operation": "computer_use",
            "error": f"Computer use failed: {str(e)}",
            "task": task,
            "environment": environment,
        }
        return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])
