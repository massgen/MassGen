# -*- coding: utf-8 -*-
"""
Gemini Computer Use tool for automating browser interactions using Google's Gemini 2.5 Computer Use model.

This tool implements browser control using the Gemini Computer Use API which allows the model to:
- Control a web browser (click, type, scroll, navigate)
- Perform multi-step workflows
- Handle safety checks and confirmations
"""

import asyncio
import base64
import json
import os
import time
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


# Screen dimensions recommended by Gemini docs
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900


def denormalize_x(x: int, screen_width: int) -> int:
    """Convert normalized x coordinate (0-1000) to actual pixel coordinate."""
    return int(x / 1000 * screen_width)


def denormalize_y(y: int, screen_height: int) -> int:
    """Convert normalized y coordinate (0-1000) to actual pixel coordinate."""
    return int(y / 1000 * screen_height)


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
            except:
                pass  # Timeout is okay
            await asyncio.sleep(1)
        
        except Exception as e:
            logger.error(f"Error executing {fname}: {e}")
            action_result = {"error": str(e)}
        
        results.append((fname, action_result))
    
    return results


async def get_gemini_function_responses(page, results):
    """Capture screenshot and create Gemini function responses.
    
    Args:
        page: Playwright page instance
        results: List of (function_name, result_dict) tuples
        
    Returns:
        List of Gemini FunctionResponse objects
    """
    screenshot_bytes = await page.screenshot(type="png")
    current_url = page.url
    function_responses = []
    
    for name, result in results:
        response_data = {"url": current_url}
        response_data.update(result)
        
        # Create function response with screenshot as inline data
        function_responses.append(
            types.FunctionResponse(
                name=name,
                response=response_data
            )
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
    Execute a browser automation task using Google's Gemini 2.5 Computer Use model.
    
    This tool implements browser control using Gemini's Computer Use API which allows
    the model to autonomously control a browser to complete tasks.
    
    Args:
        task: Description of the task to perform
        environment: Environment type - currently only "browser" is supported
        display_width: Display width in pixels (default: 1440, recommended by Gemini)
        display_height: Display height in pixels (default: 900, recommended by Gemini)
        max_iterations: Maximum number of action iterations (default: 25)
        include_thoughts: Whether to include model's thinking process (default: True)
        initial_url: Initial URL to navigate to (default: None, starts blank)
        environment_config: Additional browser configuration
        agent_cwd: Agent's current working directory
        excluded_functions: List of function names to exclude from use
        
    Returns:
        ExecutionResult containing success status, action log, and results
        
    Examples:
        # Simple search task
        gemini_computer_use("Search for Python documentation on Google")
        
        # With specific starting point
        gemini_computer_use(
            "Find pricing information",
            initial_url="https://ai.google.dev"
        )
        
    Prerequisites:
        - GEMINI_API_KEY environment variable must be set
        - Playwright must be installed: pip install playwright
        - Browsers must be installed: playwright install
    """
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
        
        # Initialize Playwright browser
        logger.info("Initializing browser...")
        playwright = await async_playwright().start()
        browser_type = environment_config.get("browser_type", "chromium")
        headless = environment_config.get("headless", True)  # Default to headless=True for server environments
        
        if browser_type == "chromium":
            browser = await playwright.chromium.launch(headless=headless)
        elif browser_type == "firefox":
            browser = await playwright.firefox.launch(headless=headless)
        elif browser_type == "webkit":
            browser = await playwright.webkit.launch(headless=headless)
        else:
            browser = await playwright.chromium.launch(headless=headless)
        
        context = await browser.new_context(viewport={"width": display_width, "height": display_height})
        page = await context.new_page()
        
        # Navigate to initial URL or blank page
        if initial_url:
            logger.info(f"Navigating to initial URL: {initial_url}")
            await page.goto(initial_url, wait_until="networkidle", timeout=10000)
        else:
            await page.goto("about:blank")
        
        logger.info(f"Initialized {browser_type} browser ({display_width}x{display_height})")
        
        # Configure Gemini with Computer Use tool
        # Using dict-based configuration as the SDK may not have direct ComputerUse class
        config_params = {
            "tools": [{
                "computer_use": {
                    "environment": "ENVIRONMENT_BROWSER"
                }
            }]
        }
        
        # Add excluded functions if specified
        if excluded_functions:
            config_params["tools"][0]["computer_use"]["excluded_predefined_functions"] = excluded_functions
        
        # Add thinking config if requested
        if include_thoughts:
            config_params["thinking_config"] = {"include_thoughts": True}
        
        config = types.GenerateContentConfig(**config_params)
        
        # Initialize conversation with task and screenshot
        initial_screenshot = await page.screenshot(type="png")
        logger.info(f"Task: {task}")
        
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=task),
                    types.Part.from_bytes(data=initial_screenshot, mime_type='image/png')
                ]
            )
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
                    model='gemini-2.5-computer-use-preview-10-2025',
                    contents=contents,
                    config=config,
                )
                
                candidate = response.candidates[0]
                contents.append(candidate.content)
                
                # Check if task is complete
                has_function_calls = any(part.function_call for part in candidate.content.parts)
                if not has_function_calls:
                    text_response = " ".join([part.text for part in candidate.content.parts if part.text])
                    logger.info(f"Agent finished: {text_response}")
                    action_log.append({
                        "iteration": iteration_count,
                        "status": "completed",
                        "final_output": text_response
                    })
                    break
                
                # Execute actions
                logger.info("Executing actions...")
                results = await execute_gemini_function_calls(candidate, page, display_width, display_height)
                
                # Log actions
                action_log.append({
                    "iteration": iteration_count,
                    "actions": [{"name": name, "result": result} for name, result in results]
                })
                
                # Capture new state
                logger.info("Capturing state...")
                function_responses, screenshot_bytes = await get_gemini_function_responses(page, results)
                
                # Add function responses and screenshot to conversation
                parts = [types.Part(function_response=fr) for fr in function_responses]
                parts.append(types.Part.from_bytes(data=screenshot_bytes, mime_type='image/png'))
                
                contents.append(
                    types.Content(
                        role="user",
                        parts=parts
                    )
                )
        
        finally:
            # Cleanup
            logger.info("\nClosing browser...")
            await browser.close()
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
                "action_log": action_log
            }
        else:
            result = {
                "success": True,
                "operation": "gemini_computer_use",
                "task": task,
                "environment": environment,
                "iterations": iteration_count,
                "action_log": action_log
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
