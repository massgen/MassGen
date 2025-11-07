# -*- coding: utf-8 -*-
"""
Claude Computer Use tool for automating browser and desktop interactions using Anthropic's Claude Computer Use API.

This tool implements browser/desktop control using Claude's Computer Use beta API which allows the model to:
- Control a web browser (click, type, scroll, navigate)
- Take screenshots and analyze the screen
- Perform multi-step workflows
- Handle safety checks and confirmations
"""

import asyncio
import base64
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
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None


# Screen dimensions recommended for Claude Computer Use
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768


def scale_coordinates(x: int, y: int, from_width: int, from_height: int, to_width: int, to_height: int):
    """Scale coordinates from one resolution to another."""
    scaled_x = int(x * to_width / from_width)
    scaled_y = int(y * to_height / from_height)
    return scaled_x, scaled_y


async def take_screenshot(page) -> str:
    """Take a screenshot and return as base64 encoded string.

    Args:
        page: Playwright page instance

    Returns:
        Base64 encoded screenshot
    """
    screenshot_bytes = await page.screenshot()
    return base64.b64encode(screenshot_bytes).decode("utf-8")


async def execute_claude_tool_use(tool_use, page, screen_width: int, screen_height: int):
    """Execute Claude Computer Use tool actions using Playwright.

    Args:
        tool_use: Claude tool use block
        page: Playwright page instance
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels

    Returns:
        Tuple of (is_screenshot, tool_result_content)
        - is_screenshot: True if this is a screenshot action
        - tool_result_content: Screenshot base64 string or text result
    """
    tool_name = tool_use.name
    tool_input = tool_use.input

    logger.info(f"  -> Executing Claude tool: {tool_name}")

    try:
        if tool_name == "computer":
            action = tool_input.get("action")
            
            if action == "screenshot":
                screenshot_b64 = await take_screenshot(page)
                logger.info(f"     Screenshot captured")
                return True, screenshot_b64  # Return flag indicating this is a screenshot
            
            elif action == "mouse_move":
                coordinate = tool_input.get("coordinate", [0, 0])
                x, y = coordinate[0], coordinate[1]
                logger.info(f"     Moving mouse to ({x}, {y})")
                await page.mouse.move(x, y)
                return False, f"Moved mouse to ({x}, {y})"
            
            elif action == "left_click":
                coordinate = tool_input.get("coordinate", [0, 0])
                x, y = coordinate[0], coordinate[1]
                logger.info(f"     Left click at ({x}, {y})")
                await page.mouse.click(x, y)
                return False, f"Clicked at ({x}, {y})"
            
            elif action == "left_click_drag":
                start = tool_input.get("coordinate", [0, 0])
                end = tool_input.get("coordinate2", [0, 0])
                logger.info(f"     Drag from ({start[0]}, {start[1]}) to ({end[0]}, {end[1]})")
                await page.mouse.move(start[0], start[1])
                await page.mouse.down()
                await page.mouse.move(end[0], end[1])
                await page.mouse.up()
                return False, f"Dragged from ({start[0]}, {start[1]}) to ({end[0]}, {end[1]})"
            
            elif action == "right_click":
                coordinate = tool_input.get("coordinate", [0, 0])
                x, y = coordinate[0], coordinate[1]
                logger.info(f"     Right click at ({x}, {y})")
                await page.mouse.click(x, y, button="right")
                return False, f"Right clicked at ({x}, {y})"
            
            elif action == "middle_click":
                coordinate = tool_input.get("coordinate", [0, 0])
                x, y = coordinate[0], coordinate[1]
                logger.info(f"     Middle click at ({x}, {y})")
                await page.mouse.click(x, y, button="middle")
                return False, f"Middle clicked at ({x}, {y})"
            
            elif action == "double_click":
                coordinate = tool_input.get("coordinate", [0, 0])
                x, y = coordinate[0], coordinate[1]
                logger.info(f"     Double click at ({x}, {y})")
                await page.mouse.dblclick(x, y)
                return False, f"Double clicked at ({x}, {y})"
            
            elif action == "triple_click":
                coordinate = tool_input.get("coordinate", [0, 0])
                x, y = coordinate[0], coordinate[1]
                logger.info(f"     Triple click at ({x}, {y})")
                await page.mouse.click(x, y, click_count=3)
                return False, f"Triple clicked at ({x}, {y})"
            
            elif action == "left_mouse_down":
                logger.info(f"     Left mouse button down")
                await page.mouse.down()
                return False, "Left mouse button pressed down"
            
            elif action == "left_mouse_up":
                logger.info(f"     Left mouse button up")
                await page.mouse.up()
                return False, "Left mouse button released"
            
            elif action == "type":
                text = tool_input.get("text", "")
                logger.info(f"     Typing: {text}")
                await page.keyboard.type(text)
                return False, f"Typed: {text}"
            
            elif action == "key":
                key = tool_input.get("text", "")
                logger.info(f"     Pressing key: {key}")
                # Convert Claude key format to Playwright format
                key_map = {
                    "Return": "Enter",
                    "Escape": "Escape",
                    "BackSpace": "Backspace",
                    "Tab": "Tab",
                    "Space": " ",
                }
                playwright_key = key_map.get(key, key)
                await page.keyboard.press(playwright_key)
                return False, f"Pressed key: {key}"
            
            elif action == "hold_key":
                key = tool_input.get("text", "")
                logger.info(f"     Holding key: {key}")
                key_map = {
                    "Return": "Enter",
                    "Escape": "Escape",
                    "BackSpace": "Backspace",
                    "Tab": "Tab",
                    "Space": " ",
                }
                playwright_key = key_map.get(key, key)
                await page.keyboard.down(playwright_key)
                return False, f"Holding key: {key}"
            
            elif action == "scroll":
                direction = tool_input.get("direction", "down")
                amount = tool_input.get("amount", 5)
                logger.info(f"     Scrolling {direction} by {amount}")
                
                if direction == "down":
                    await page.mouse.wheel(0, amount * 100)
                elif direction == "up":
                    await page.mouse.wheel(0, -amount * 100)
                elif direction == "left":
                    await page.mouse.wheel(-amount * 100, 0)
                elif direction == "right":
                    await page.mouse.wheel(amount * 100, 0)
                
                return False, f"Scrolled {direction} by {amount}"
            
            elif action == "wait":
                delay = tool_input.get("delay", 1000)  # milliseconds
                logger.info(f"     Waiting {delay}ms")
                await asyncio.sleep(delay / 1000)
                return False, f"Waited {delay}ms"
            
            elif action == "cursor_position":
                return False, "Cursor position tracking not available in browser environment"
            
            else:
                return False, f"Unknown computer action: {action}"
        
        elif tool_name == "bash":
            command = tool_input.get("command", "")
            logger.warning(f"     Bash execution not supported in browser-only environment: {command}")
            return False, "Bash commands are not available in browser-only environment. Use a Docker/Linux environment for full computer use capabilities."
        
        elif tool_name == "str_replace_editor":
            logger.warning(f"     File editor not supported in browser-only environment")
            return False, "File editing is not available in browser-only environment. Use a Docker/Linux environment for full computer use capabilities."
        
        else:
            return False, f"Unknown tool: {tool_name}"
    
    except Exception as e:
        logger.error(f"Error executing {tool_name}: {e}")
        return False, f"Error: {str(e)}"


async def claude_computer_use(
    query: str,
    environment: str = "browser",
    display_width: int = SCREEN_WIDTH,
    display_height: int = SCREEN_HEIGHT,
    max_iterations: int = 25,
    headless: bool = True,
    browser_type: str = "chromium",
    **kwargs,
) -> ExecutionResult:
    """
    Execute Claude Computer Use to automate browser or desktop tasks.

    Args:
        query: The task description for Claude to execute
        environment: Environment type ("browser", "linux", "mac", "windows")
        display_width: Screen width in pixels (default: 1024)
        display_height: Screen height in pixels (default: 768)
        max_iterations: Maximum number of agent loop iterations (default: 25)
        headless: Run browser in headless mode (default: True)
        browser_type: Browser to use - "chromium", "firefox", or "webkit" (default: "chromium")
        **kwargs: Additional parameters

    Returns:
        ExecutionResult containing the final answer and any intermediate results

    Example:
        >>> result = await claude_computer_use(
        ...     query="Search for Python documentation on the web",
        ...     environment="browser",
        ...     display_width=1024,
        ...     display_height=768
        ... )
    """
    # Force headless mode on Linux systems without DISPLAY
    import platform
    if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
        if not headless:
            logger.warning("Forcing headless=True on Linux system without DISPLAY environment variable")
            headless = True
    
    # Check dependencies
    if not PLAYWRIGHT_AVAILABLE:
        error_msg = "Playwright is not installed. Install with: pip install playwright && playwright install"
        logger.error(error_msg)
        return ExecutionResult(
            output_blocks=[TextContent(data=error_msg)],
        )

    if not ANTHROPIC_AVAILABLE:
        error_msg = "Anthropic SDK is not installed. Install with: pip install anthropic"
        logger.error(error_msg)
        return ExecutionResult(
            output_blocks=[TextContent(data=error_msg)],
        )

    # Load environment variables
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        error_msg = "ANTHROPIC_API_KEY environment variable not set"
        logger.error(error_msg)
        return ExecutionResult(
            output_blocks=[TextContent(data=error_msg)],
        )

    # Only browser environment is currently supported
    if environment != "browser":
        error_msg = f"Environment '{environment}' is not supported. Only 'browser' environment is currently available."
        logger.warning(error_msg)
        return ExecutionResult(
            output_blocks=[TextContent(data=error_msg)],
        )

    logger.info(f"Starting Claude Computer Use with query: {query}")
    logger.info(f"Environment: {environment}, Display: {display_width}x{display_height}, Max iterations: {max_iterations}")

    # Initialize Anthropic client
    client = Anthropic(api_key=api_key)

    # Initialize Playwright
    playwright = await async_playwright().start()
    
    # Launch browser
    browser_launcher = getattr(playwright, browser_type)
    browser = await browser_launcher.launch(headless=headless)
    context = await browser.new_context(
        viewport={"width": display_width, "height": display_height}
    )
    page = await context.new_page()
    
    # Navigate to a starting page
    await page.goto("about:blank")

    try:
        # Claude Computer Use tool definitions (schema-less tools)
        # These are Anthropic's built-in tools with the computer-use-2025-01-24 beta
        tools = [
            {
                "type": "computer_20250124",
                "name": "computer",
                "display_width_px": display_width,
                "display_height_px": display_height,
                "display_number": 1,
            },
            {
                "type": "bash_20250124",
                "name": "bash",
            },
            {
                "type": "text_editor_20250728",
                "name": "str_replace_based_edit_tool",
            },
        ]

        # Initialize conversation with the user query
        messages = [
            {
                "role": "user",
                "content": query,
            }
        ]

        iteration = 0
        final_answer = None

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"\n=== Iteration {iteration}/{max_iterations} ===")

            # Call Claude API using beta endpoint
            response = client.beta.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                tools=tools,
                betas=["computer-use-2025-01-24"],
                messages=messages,
            )

            logger.info(f"Claude response stop_reason: {response.stop_reason}")

            # Check if we're done
            if response.stop_reason == "end_turn":
                # Extract final text answer
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text
                
                final_answer = final_text
                logger.info(f"Task completed: {final_answer}")
                break

            # Process tool uses
            if response.stop_reason == "tool_use":
                # Add assistant message to conversation
                messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                # Execute tool uses and collect results
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        is_screenshot, result = await execute_claude_tool_use(
                            block,
                            page,
                            display_width,
                            display_height,
                        )
                        
                        # Handle screenshot differently (return as image)
                        if is_screenshot:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "image/png",
                                            "data": result,
                                        },
                                    }
                                ],
                            })
                        else:
                            # Regular tool result (text)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(result),
                            })

                # Add tool results to conversation
                messages.append({
                    "role": "user",
                    "content": tool_results,
                })

            else:
                # Unexpected stop reason
                logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
                final_answer = f"Stopped unexpectedly: {response.stop_reason}"
                break

        if iteration >= max_iterations:
            final_answer = f"Reached maximum iterations ({max_iterations}) without completing the task."
            logger.warning(final_answer)

        # Return result
        return ExecutionResult(
            output_blocks=[TextContent(data=final_answer or "Task completed")],
        )

    except Exception as e:
        error_msg = f"Error during Claude Computer Use execution: {str(e)}"
        logger.error(error_msg)
        logger.exception(e)
        return ExecutionResult(
            output_blocks=[TextContent(data=error_msg)],
        )

    finally:
        # Cleanup
        await context.close()
        await browser.close()
        await playwright.stop()
        logger.info("Claude Computer Use session ended")
