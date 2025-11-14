# -*- coding: utf-8 -*-
"""
Gemini Computer Use tool for automating browser interactions using Google's Gemini 2.5 Computer Use model.

This tool implements browser control using the Gemini Computer Use API which allows the model to:
- Control a web browser (click, type, scroll, navigate)
- Perform multi-step workflows
- Handle safety checks and confirmations
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from massgen.logger_config import logger
from massgen.tool._result import ExecutionResult, TextContent

# Optional dependencies with graceful fallback
try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None

try:
    from google import genai
    from google.genai import types

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None
    types = None

try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None


# Screen dimensions recommended by Gemini docs
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900


def denormalize_x(x: int, screen_width: int) -> int:
    """Convert normalized x coordinate (0-1000) to actual pixel coordinate."""
    return int(x / 1000 * screen_width)


def denormalize_y(y: int, screen_height: int) -> int:
    """Convert normalized y coordinate (0-1000) to actual pixel coordinate."""
    return int(y / 1000 * screen_height)


def take_screenshot_docker(container, display: str = ":99") -> bytes:
    """Take a screenshot from Docker container using scrot.

    Args:
        container: Docker container instance
        display: X11 display number

    Returns:
        Screenshot as bytes
    """
    import time

    # Remove old screenshot if exists
    container.exec_run("rm -f /tmp/screenshot.png")

    # Take screenshot with scrot (use environment parameter)
    result = container.exec_run(
        "scrot /tmp/screenshot.png",
        environment={"DISPLAY": display},
    )

    if result.exit_code != 0:
        logger.error(f"Screenshot command failed: {result.output}")
        # Try alternative method with import
        result = container.exec_run(
            "import -window root /tmp/screenshot.png",
            environment={"DISPLAY": display},
        )
        if result.exit_code != 0:
            logger.error(f"Alternative screenshot also failed: {result.output}")
            return b""

    # Small delay to ensure file is written
    time.sleep(0.2)

    # Verify screenshot exists and has content
    check_result = container.exec_run("ls -lh /tmp/screenshot.png")
    logger.info(f"Screenshot file info: {check_result.output.decode()}")

    # Read the screenshot
    read_result = container.exec_run("cat /tmp/screenshot.png", stdout=True)
    if read_result.exit_code != 0:
        logger.error(f"Failed to read screenshot: {read_result.output}")
        return b""

    screenshot_bytes = read_result.output

    # Verify we got actual image data
    if len(screenshot_bytes) < 1000:  # PNG should be at least a few KB
        logger.error(f"Screenshot too small ({len(screenshot_bytes)} bytes), likely invalid")
        return b""

    # Verify PNG header
    if not screenshot_bytes.startswith(b"\x89PNG"):
        logger.error("Screenshot does not have valid PNG header")
        return b""

    logger.info(f"Successfully captured screenshot: {len(screenshot_bytes)} bytes")
    return screenshot_bytes


def execute_docker_action(container, action_name: str, args: Dict[str, Any], screen_width: int, screen_height: int, display: str = ":99") -> Dict[str, Any]:
    """Execute a Gemini action in Docker using xdotool.

    Args:
        container: Docker container instance
        action_name: Name of the Gemini action
        args: Action arguments
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
        display: X11 display number

    Returns:
        Result dictionary
    """
    import time

    result = {}
    try:
        if action_name == "open_web_browser":
            # Browser should already be open
            pass

        elif action_name == "click_at":
            x = args.get("x", 0)
            y = args.get("y", 0)
            actual_x = denormalize_x(x, screen_width)
            actual_y = denormalize_y(y, screen_height)
            logger.info(f"     Docker click at ({actual_x}, {actual_y})")
            container.exec_run(
                f"xdotool mousemove {actual_x} {actual_y} click 1",
                environment={"DISPLAY": display},
            )

        elif action_name == "hover_at":
            x = args.get("x", 0)
            y = args.get("y", 0)
            actual_x = denormalize_x(x, screen_width)
            actual_y = denormalize_y(y, screen_height)
            logger.info(f"     Docker hover at ({actual_x}, {actual_y})")
            container.exec_run(
                f"xdotool mousemove {actual_x} {actual_y}",
                environment={"DISPLAY": display},
            )

        elif action_name == "type_text_at":
            x = args.get("x", 0)
            y = args.get("y", 0)
            text = args.get("text", "")
            press_enter = args.get("press_enter", True)
            clear_before_typing = args.get("clear_before_typing", True)

            actual_x = denormalize_x(x, screen_width)
            actual_y = denormalize_y(y, screen_height)
            logger.info(f"     Docker type '{text}' at ({actual_x}, {actual_y})")

            # Click to focus
            container.exec_run(
                f"xdotool mousemove {actual_x} {actual_y} click 1",
                environment={"DISPLAY": display},
            )

            if clear_before_typing:
                # Select all and delete
                container.exec_run("xdotool key ctrl+a", environment={"DISPLAY": display})
                container.exec_run("xdotool key BackSpace", environment={"DISPLAY": display})

            # Type text (escape special characters)
            escaped_text = text.replace("'", "'\\''")
            container.exec_run(
                f"xdotool type '{escaped_text}'",
                environment={"DISPLAY": display},
            )

            if press_enter:
                container.exec_run("xdotool key Return", environment={"DISPLAY": display})

        elif action_name == "key_combination":
            keys = args.get("keys", "")
            logger.info(f"     Docker press keys: {keys}")
            # Convert to xdotool format (e.g., "Control+A" -> "ctrl+a")
            xdotool_keys = keys.replace("Control", "ctrl").replace("Shift", "shift").replace("Alt", "alt")
            container.exec_run(
                f"xdotool key {xdotool_keys}",
                environment={"DISPLAY": display},
            )

        elif action_name == "scroll_document":
            direction = args.get("direction", "down")
            logger.info(f"     Docker scroll document: {direction}")

            if direction == "down":
                cmd = "xdotool key Page_Down"
            elif direction == "up":
                cmd = "xdotool key Page_Up"
            elif direction == "left":
                cmd = "xdotool key Left Left Left"
            elif direction == "right":
                cmd = "xdotool key Right Right Right"
            else:
                cmd = "xdotool key Page_Down"

            container.exec_run(cmd, environment={"DISPLAY": display})

        elif action_name == "scroll_at":
            x = args.get("x", 0)
            y = args.get("y", 0)
            direction = args.get("direction", "down")

            actual_x = denormalize_x(x, screen_width)
            actual_y = denormalize_y(y, screen_height)
            logger.info(f"     Docker scroll at ({actual_x}, {actual_y}) {direction}")

            # Move mouse to position
            container.exec_run(
                f"xdotool mousemove {actual_x} {actual_y}",
                environment={"DISPLAY": display},
            )

            # Scroll with mouse wheel
            if direction == "down":
                cmd = "xdotool click 5 click 5 click 5"  # Scroll down
            elif direction == "up":
                cmd = "xdotool click 4 click 4 click 4"  # Scroll up
            else:
                cmd = "xdotool click 5 click 5 click 5"

            container.exec_run(cmd, environment={"DISPLAY": display})

        elif action_name == "navigate":
            url = args.get("url", "")
            logger.info(f"     Docker navigate to: {url}")
            # Focus address bar and type URL
            container.exec_run("xdotool key ctrl+l", environment={"DISPLAY": display})
            time.sleep(0.5)
            escaped_url = url.replace("'", "'\\''")
            container.exec_run(
                f"xdotool type '{escaped_url}'",
                environment={"DISPLAY": display},
            )
            container.exec_run("xdotool key Return", environment={"DISPLAY": display})

        elif action_name == "go_back":
            logger.info("     Docker go back")
            container.exec_run("xdotool key alt+Left", environment={"DISPLAY": display})

        elif action_name == "go_forward":
            logger.info("     Docker go forward")
            container.exec_run("xdotool key alt+Right", environment={"DISPLAY": display})

        elif action_name == "search":
            logger.info("     Docker navigate to search")
            # Navigate to Google
            container.exec_run("xdotool key ctrl+l", environment={"DISPLAY": display})
            time.sleep(0.5)
            container.exec_run(
                "xdotool type 'https://www.google.com'",
                environment={"DISPLAY": display},
            )
            container.exec_run("xdotool key Return", environment={"DISPLAY": display})

        elif action_name == "wait_5_seconds":
            logger.info("     Docker wait 5 seconds")
            time.sleep(5)

        elif action_name == "drag_and_drop":
            x = args.get("x", 0)
            y = args.get("y", 0)
            dest_x = args.get("destination_x", 0)
            dest_y = args.get("destination_y", 0)

            actual_x = denormalize_x(x, screen_width)
            actual_y = denormalize_y(y, screen_height)
            actual_dest_x = denormalize_x(dest_x, screen_width)
            actual_dest_y = denormalize_y(dest_y, screen_height)

            logger.info(f"     Docker drag from ({actual_x}, {actual_y}) to ({actual_dest_x}, {actual_dest_y})")
            container.exec_run(
                f"xdotool mousemove {actual_x} {actual_y} mousedown 1 mousemove {actual_dest_x} {actual_dest_y} mouseup 1",
                environment={"DISPLAY": display},
            )

        else:
            logger.warning(f"     Docker: Unimplemented function {action_name}")
            result = {"error": f"Unimplemented function: {action_name}"}

        # Small delay after action
        time.sleep(1)

    except Exception as e:
        logger.error(f"Docker action {action_name} failed: {e}")
        result = {"error": str(e)}

    return result


def execute_gemini_function_calls_docker(candidate, container, screen_width: int, screen_height: int, display: str = ":99"):
    """Execute Gemini Computer Use function calls in Docker using xdotool.

    Args:
        candidate: Gemini response candidate
        container: Docker container instance
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
        display: X11 display number

    Returns:
        List of (function_name, result_dict) tuples
    """
    results = []
    function_calls = []

    for part in candidate.content.parts:
        if part.function_call:
            function_calls.append(part.function_call)

    for function_call in function_calls:
        fname = function_call.name
        args = function_call.args
        logger.info(f"  -> Executing Gemini action in Docker: {fname}")

        action_result = execute_docker_action(container, fname, args, screen_width, screen_height, display)
        results.append((fname, action_result))

    return results


def get_gemini_function_responses_docker(container, results, function_calls, display: str = ":99"):
    """Capture screenshot from Docker and create Gemini function responses.

    Args:
        container: Docker container instance
        results: List of (function_name, result_dict) tuples
        function_calls: List of function call objects from candidate
        display: X11 display number

    Returns:
        Tuple of (function_responses, screenshot_bytes)
    """
    screenshot_bytes = take_screenshot_docker(container, display)
    function_responses = []

    for (name, result), function_call in zip(results, function_calls):
        # Gemini API requires URL field even for Docker environment
        response_data = {"url": "about:blank"}  # Placeholder URL for Docker
        response_data.update(result)

        # Check if this function call has a safety decision in its args
        try:
            if hasattr(function_call, "args") and function_call.args is not None:
                # Convert args to dict if it's not already
                args_dict = dict(function_call.args) if hasattr(function_call.args, "__iter__") else function_call.args
                if isinstance(args_dict, dict) and "safety_decision" in args_dict:
                    safety_decision = args_dict["safety_decision"]
                    logger.info(f"     Function {name} has safety decision: {safety_decision}")
                    # Add safety acknowledgement to response
                    response_data["safety_acknowledgement"] = "true"
        except (TypeError, AttributeError) as e:
            logger.debug(f"     Could not check safety decision for {name}: {e}")

        # Create function response
        function_responses.append(
            types.FunctionResponse(
                id=function_call.id,
                name=name,
                response=response_data,
            ),
        )

    return function_responses, screenshot_bytes


async def execute_gemini_function_calls(candidate, page, screen_width: int, screen_height: int):
    """Execute Gemini Computer Use function calls using Playwright.

    Args:
        candidate: Gemini response candidate
        page: Playwright page instance
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels

    Returns:
        List of (function_name, result_dict) tuples
    """
    results = []
    function_calls = []

    for part in candidate.content.parts:
        if part.function_call:
            function_calls.append(part.function_call)

    for function_call in function_calls:
        action_result = {}
        fname = function_call.name
        args = function_call.args
        logger.info(f"  -> Executing Gemini action: {fname}")

        try:
            if fname == "open_web_browser":
                # Already open
                pass

            elif fname == "click_at":
                x = args.get("x", 0)
                y = args.get("y", 0)
                actual_x = denormalize_x(x, screen_width)
                actual_y = denormalize_y(y, screen_height)
                logger.info(f"     Click at ({actual_x}, {actual_y}) [normalized: ({x}, {y})]")
                await page.mouse.click(actual_x, actual_y)

            elif fname == "hover_at":
                x = args.get("x", 0)
                y = args.get("y", 0)
                actual_x = denormalize_x(x, screen_width)
                actual_y = denormalize_y(y, screen_height)
                logger.info(f"     Hover at ({actual_x}, {actual_y})")
                await page.mouse.move(actual_x, actual_y)

            elif fname == "type_text_at":
                x = args.get("x", 0)
                y = args.get("y", 0)
                text = args.get("text", "")
                press_enter = args.get("press_enter", True)
                clear_before_typing = args.get("clear_before_typing", True)

                actual_x = denormalize_x(x, screen_width)
                actual_y = denormalize_y(y, screen_height)
                logger.info(f"     Type '{text}' at ({actual_x}, {actual_y})")

                await page.mouse.click(actual_x, actual_y)

                if clear_before_typing:
                    # Clear field (Meta+A for Mac, Control+A for others, then Backspace)
                    await page.keyboard.press("Meta+A")
                    await page.keyboard.press("Backspace")

                await page.keyboard.type(text)

                if press_enter:
                    await page.keyboard.press("Enter")

            elif fname == "key_combination":
                keys = args.get("keys", "")
                logger.info(f"     Press keys: {keys}")
                await page.keyboard.press(keys)

            elif fname == "scroll_document":
                direction = args.get("direction", "down")
                logger.info(f"     Scroll document: {direction}")

                if direction == "down":
                    await page.evaluate("window.scrollBy(0, 500)")
                elif direction == "up":
                    await page.evaluate("window.scrollBy(0, -500)")
                elif direction == "left":
                    await page.evaluate("window.scrollBy(-500, 0)")
                elif direction == "right":
                    await page.evaluate("window.scrollBy(500, 0)")

            elif fname == "scroll_at":
                x = args.get("x", 0)
                y = args.get("y", 0)
                direction = args.get("direction", "down")
                magnitude = args.get("magnitude", 800)

                actual_x = denormalize_x(x, screen_width)
                actual_y = denormalize_y(y, screen_height)
                actual_magnitude = denormalize_y(magnitude, screen_height)  # Use height for scroll amount

                logger.info(f"     Scroll at ({actual_x}, {actual_y}) {direction} by {actual_magnitude}px")

                await page.mouse.move(actual_x, actual_y)

                if direction == "down":
                    await page.evaluate(f"window.scrollBy(0, {actual_magnitude})")
                elif direction == "up":
                    await page.evaluate(f"window.scrollBy(0, -{actual_magnitude})")
                elif direction == "left":
                    await page.evaluate(f"window.scrollBy(-{actual_magnitude}, 0)")
                elif direction == "right":
                    await page.evaluate(f"window.scrollBy({actual_magnitude}, 0)")

            elif fname == "navigate":
                url = args.get("url", "")
                logger.info(f"     Navigate to: {url}")
                await page.goto(url, wait_until="networkidle", timeout=10000)

            elif fname == "go_back":
                logger.info("     Go back")
                await page.go_back()

            elif fname == "go_forward":
                logger.info("     Go forward")
                await page.go_forward()

            elif fname == "search":
                logger.info("     Navigate to search")
                await page.goto("https://www.google.com")

            elif fname == "wait_5_seconds":
                logger.info("     Wait 5 seconds")
                await asyncio.sleep(5)

            elif fname == "drag_and_drop":
                x = args.get("x", 0)
                y = args.get("y", 0)
                dest_x = args.get("destination_x", 0)
                dest_y = args.get("destination_y", 0)

                actual_x = denormalize_x(x, screen_width)
                actual_y = denormalize_y(y, screen_height)
                actual_dest_x = denormalize_x(dest_x, screen_width)
                actual_dest_y = denormalize_y(dest_y, screen_height)

                logger.info(f"     Drag from ({actual_x}, {actual_y}) to ({actual_dest_x}, {actual_dest_y})")
                await page.mouse.move(actual_x, actual_y)
                await page.mouse.down()
                await page.mouse.move(actual_dest_x, actual_dest_y)
                await page.mouse.up()

            else:
                logger.warning(f"Warning: Unimplemented function {fname}")
                action_result = {"error": f"Unimplemented function: {fname}"}

            # Wait for potential navigations/renders
            try:
                await page.wait_for_load_state(timeout=5000)
            except Exception:
                pass  # Timeout is okay
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error executing {fname}: {e}")
            action_result = {"error": str(e)}

        results.append((fname, action_result))

    return results


async def get_gemini_function_responses(page, results, function_calls):
    """Capture screenshot and create Gemini function responses.

    Args:
        page: Playwright page instance
        results: List of (function_name, result_dict) tuples
        function_calls: List of function call objects from candidate

    Returns:
        Tuple of (function_responses, screenshot_bytes)
    """
    screenshot_bytes = await page.screenshot(type="png")
    current_url = page.url
    function_responses = []

    for (name, result), function_call in zip(results, function_calls):
        response_data = {"url": current_url}
        response_data.update(result)

        # Check if this function call has a safety decision in its args
        try:
            if hasattr(function_call, "args") and function_call.args is not None:
                # Convert args to dict if it's not already
                args_dict = dict(function_call.args) if hasattr(function_call.args, "__iter__") else function_call.args
                if isinstance(args_dict, dict) and "safety_decision" in args_dict:
                    safety_decision = args_dict["safety_decision"]
                    logger.info(f"     Function {name} has safety decision: {safety_decision}")
                    # Add safety acknowledgement to response
                    response_data["safety_acknowledgement"] = "true"
        except (TypeError, AttributeError) as e:
            logger.debug(f"     Could not check safety decision for {name}: {e}")

        # Create function response
        function_responses.append(
            types.FunctionResponse(
                id=function_call.id,
                name=name,
                response=response_data,
            ),
        )

    return function_responses, screenshot_bytes


async def gemini_computer_use(
    task: str,
    environment: str = "browser",
    display_width: int = 1440,
    display_height: int = 900,
    max_iterations: int = 25,
    include_thoughts: bool = True,
    initial_url: Optional[str] = None,
    environment_config: Optional[Dict[str, Any]] = None,
    agent_cwd: Optional[str] = None,
    excluded_functions: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Execute a browser or Docker automation task using Google's Gemini 2.5 Computer Use model.

    This tool implements control using Gemini's Computer Use API which allows
    the model to autonomously control a browser or Linux desktop to complete tasks.

    Args:
        task: Description of the task to perform
        environment: Environment type - "browser" or "linux" (Docker)
        display_width: Display width in pixels (default: 1440, recommended by Gemini)
        display_height: Display height in pixels (default: 900, recommended by Gemini)
        max_iterations: Maximum number of action iterations (default: 25)
        include_thoughts: Whether to include model's thinking process (default: True)
        initial_url: Initial URL to navigate to (browser only, default: None)
        environment_config: Additional configuration (browser: headless/browser_type, docker: container_name/display)
        agent_cwd: Agent's current working directory
        excluded_functions: List of function names to exclude from use

    Returns:
        ExecutionResult containing success status, action log, and results

    Examples:
        # Browser task
        gemini_computer_use("Search for Python documentation on Google", environment="browser")

        # Docker task
        gemini_computer_use(
            "Open Firefox and browse to GitHub",
            environment="linux",
            environment_config={"container_name": "cua-container", "display": ":99"}
        )

    Prerequisites:
        - GEMINI_API_KEY environment variable must be set
        - For browser: pip install playwright && playwright install
        - For Docker: Docker container with X11 and xdotool installed
    """
    # Check environment-specific dependencies
    if environment == "linux":
        if not DOCKER_AVAILABLE:
            result = {
                "success": False,
                "operation": "gemini_computer_use",
                "error": "Docker not installed. Install with: pip install docker",
            }
            return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])
    else:  # browser
        if not PLAYWRIGHT_AVAILABLE:
            result = {
                "success": False,
                "operation": "gemini_computer_use",
                "error": "Playwright not installed. Install with: pip install playwright && playwright install",
            }
            return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

    if not GENAI_AVAILABLE:
        result = {
            "success": False,
            "operation": "gemini_computer_use",
            "error": "Google GenAI SDK not installed. Install with: pip install google-genai",
        }
        return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

    environment_config = environment_config or {}
    excluded_functions = excluded_functions or []

    try:
        # Load environment variables
        script_dir = Path(__file__).parent.parent.parent.parent
        env_path = script_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            result = {
                "success": False,
                "operation": "gemini_computer_use",
                "error": "Gemini API key not found. Please set GEMINI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

        # Initialize Gemini client
        client = genai.Client(api_key=gemini_api_key)

        # Initialize environment (browser or Docker)
        container = None
        display = None
        page = None
        playwright = None
        browser = None

        if environment == "linux":
            # Docker environment
            logger.info("Initializing Docker environment...")
            container_name = environment_config.get("container_name", "cua-container")
            display = environment_config.get("display", ":99")

            docker_client = docker.from_env()
            try:
                container = docker_client.containers.get(container_name)
                if container.status != "running":
                    logger.info(f"Starting container {container_name}...")
                    container.start()
                logger.info(f"Using Docker container: {container_name} (display {display})")
            except docker.errors.NotFound:
                result = {
                    "success": False,
                    "operation": "gemini_computer_use",
                    "error": f"Docker container '{container_name}' not found. Please create it first.",
                }
                return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

            # Take initial screenshot from Docker
            initial_screenshot = take_screenshot_docker(container, display)

            # Verify screenshot was captured
            if not initial_screenshot or len(initial_screenshot) < 1000:
                result = {
                    "success": False,
                    "operation": "gemini_computer_use",
                    "error": f"Failed to capture screenshot from Docker container. Check if X11 display {display} is running and scrot is installed.",
                }
                return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

        else:
            # Browser environment
            logger.info("Initializing browser...")
            playwright = await async_playwright().start()
            browser_type = environment_config.get("browser_type", "chromium")
            headless = environment_config.get("headless", True)

            # Prepare launch options
            launch_options = {"headless": headless}

            # If not headless and DISPLAY is set, log it
            if not headless:
                display_env = os.environ.get("DISPLAY")
                if display_env:
                    logger.info(f"Running browser with DISPLAY={display_env} (environment variable)")
                else:
                    logger.warning("headless=false but DISPLAY not set. Browser window may not be visible.")

            if browser_type == "chromium":
                browser = await playwright.chromium.launch(**launch_options)
            elif browser_type == "firefox":
                browser = await playwright.firefox.launch(**launch_options)
            elif browser_type == "webkit":
                browser = await playwright.webkit.launch(**launch_options)
            else:
                browser = await playwright.chromium.launch(**launch_options)

            context = await browser.new_context(viewport={"width": display_width, "height": display_height})
            page = await context.new_page()

            # Navigate to initial URL or blank page
            if initial_url:
                logger.info(f"Navigating to initial URL: {initial_url}")
                await page.goto(initial_url, wait_until="networkidle", timeout=10000)
            else:
                await page.goto("about:blank")

            logger.info(f"Initialized {browser_type} browser ({display_width}x{display_height})")

            # Take initial screenshot from browser
            initial_screenshot = await page.screenshot(type="png")

        # Configure Gemini with Computer Use tool
        config_params = {
            "tools": [
                {
                    "computer_use": {
                        "environment": "ENVIRONMENT_BROWSER" if environment == "browser" else "ENVIRONMENT_BROWSER",
                    },
                },
            ],
        }

        # Add excluded functions if specified
        if excluded_functions:
            config_params["tools"][0]["computer_use"]["excluded_predefined_functions"] = excluded_functions

        # Add thinking config if requested
        if include_thoughts:
            config_params["thinking_config"] = {"include_thoughts": True}

        config = types.GenerateContentConfig(**config_params)

        # Initialize conversation with task and screenshot
        logger.info(f"Task: {task} (environment: {environment})")

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=task),
                    types.Part.from_bytes(data=initial_screenshot, mime_type="image/png"),
                ],
            ),
        ]

        # Agent loop
        action_log = []
        iteration_count = 0

        try:
            for i in range(max_iterations):
                iteration_count = i + 1
                logger.info(f"\n--- Gemini Computer Use Turn {iteration_count}/{max_iterations} ---")
                logger.info("Thinking...")

                response = client.models.generate_content(
                    model="gemini-2.5-computer-use-preview-10-2025",
                    contents=contents,
                    config=config,
                )

                # Check if response has candidates
                if not response.candidates or len(response.candidates) == 0:
                    logger.error("No candidates in response")
                    raise Exception("No candidates returned from Gemini API")

                candidate = response.candidates[0]

                # Check if candidate has content
                if not candidate.content or not candidate.content.parts:
                    logger.error("No content or parts in candidate")
                    raise Exception("Empty content returned from Gemini API")

                contents.append(candidate.content)

                # Check if task is complete
                has_function_calls = any(part.function_call for part in candidate.content.parts)
                if not has_function_calls:
                    text_response = " ".join([part.text for part in candidate.content.parts if part.text])
                    logger.info(f"Agent finished: {text_response}")
                    action_log.append(
                        {
                            "iteration": iteration_count,
                            "status": "completed",
                            "final_output": text_response,
                        },
                    )
                    break

                # Execute actions based on environment
                logger.info("Executing actions...")
                if environment == "linux":
                    # Docker execution
                    results = execute_gemini_function_calls_docker(candidate, container, display_width, display_height, display)
                else:
                    # Browser execution
                    results = await execute_gemini_function_calls(candidate, page, display_width, display_height)

                # Extract function calls for safety decision handling
                function_calls = [part.function_call for part in candidate.content.parts if part.function_call]

                # Log actions
                action_log.append(
                    {
                        "iteration": iteration_count,
                        "actions": [{"name": name, "result": result} for name, result in results],
                    },
                )

                # Capture new state
                logger.info("Capturing state...")
                if environment == "linux":
                    function_responses, screenshot_bytes = get_gemini_function_responses_docker(container, results, function_calls, display)
                else:
                    function_responses, screenshot_bytes = await get_gemini_function_responses(page, results, function_calls)

                # Add function responses and screenshot to conversation
                parts = [types.Part(function_response=fr) for fr in function_responses]
                parts.append(types.Part.from_bytes(data=screenshot_bytes, mime_type="image/png"))

                contents.append(
                    types.Content(
                        role="user",
                        parts=parts,
                    ),
                )

        finally:
            # Cleanup
            if environment == "linux":
                logger.info("\nDocker environment cleanup complete")
            else:
                logger.info("\nClosing browser...")
                if browser:
                    await browser.close()
                if playwright:
                    await playwright.stop()

        # Prepare result
        if iteration_count >= max_iterations:
            result = {
                "success": False,
                "operation": "gemini_computer_use",
                "error": f"Reached maximum iterations ({max_iterations})",
                "task": task,
                "environment": environment,
                "iterations": iteration_count,
                "action_log": action_log,
            }
        else:
            result = {
                "success": True,
                "operation": "gemini_computer_use",
                "task": task,
                "environment": environment,
                "iterations": iteration_count,
                "action_log": action_log,
            }

        return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

    except Exception as e:
        logger.error(f"Gemini computer use failed: {str(e)}")
        result = {
            "success": False,
            "operation": "gemini_computer_use",
            "error": f"Gemini computer use failed: {str(e)}",
            "task": task,
            "environment": environment,
        }
        return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])
