# -*- coding: utf-8 -*-
"""
Simple browser automation tool that works with any LLM model.

This tool provides basic browser automation without requiring OpenAI's hosted computer_use_preview tool.
It works with gpt-4.1, gpt-4o, Gemini, and other models.
"""

import asyncio
import base64
import json
from typing import Any, Dict, Optional

from massgen.logger_config import logger
from massgen.tool._result import ExecutionResult, TextContent

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


async def browser_automation(
    task: str,
    url: Optional[str] = None,
    action: str = "navigate",
    selector: Optional[str] = None,
    text: Optional[str] = None,
    headless: bool = False,
    screenshot: bool = True,
    **kwargs,
) -> ExecutionResult:
    """
    Perform browser automation tasks using Playwright.

    This is a simple browser automation tool that works with any LLM model (gpt-4.1, gpt-4o, Gemini, etc.)
    without requiring OpenAI's hosted computer_use_preview tool.

    Args:
        task: Description of what to do (for logging/context)
        url: URL to navigate to
        action: Action to perform - "navigate", "click", "type", "screenshot", "extract"
        selector: CSS selector for element to interact with
        text: Text to type (for "type" action)
        headless: Run browser in headless mode
        screenshot: Take screenshot after action
        **kwargs: Additional parameters

    Returns:
        ExecutionResult with action results and optional screenshot

    Example:
        # Navigate to a page
        result = await browser_automation(
            task="Open Wikipedia",
            url="https://en.wikipedia.org",
            action="navigate"
        )

        # Click an element
        result = await browser_automation(
            task="Click search button",
            action="click",
            selector="button[type='submit']"
        )

        # Type text
        result = await browser_automation(
            task="Search for Jimmy Carter",
            action="type",
            selector="input[name='search']",
            text="Jimmy Carter"
        )

        # Extract text
        result = await browser_automation(
            task="Get page title",
            action="extract",
            selector="h1"
        )
    """
    if not PLAYWRIGHT_AVAILABLE:
        result = {
            "success": False,
            "operation": "browser_automation",
            "error": "Playwright not installed. Install with: pip install playwright && playwright install",
        }
        return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

    result_data = {
        "success": False,
        "operation": "browser_automation",
        "task": task,
        "action": action,
    }

    try:
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            page = await context.new_page()

            logger.info(f"Browser automation: {action} - {task}")

            # Perform action
            if action == "navigate":
                if not url:
                    raise ValueError("URL required for navigate action")
                await page.goto(url, wait_until="networkidle")
                result_data["url"] = url
                result_data["title"] = await page.title()
                logger.info(f"Navigated to: {url} - {result_data['title']}")

            elif action == "click":
                if not selector:
                    raise ValueError("Selector required for click action")
                await page.click(selector)
                logger.info(f"Clicked: {selector}")

            elif action == "type":
                if not selector or not text:
                    raise ValueError("Selector and text required for type action")
                await page.fill(selector, text)
                logger.info(f"Typed '{text}' into: {selector}")

            elif action == "extract":
                if not selector:
                    raise ValueError("Selector required for extract action")
                elements = await page.query_selector_all(selector)
                extracted_text = []
                for elem in elements[:10]:  # Limit to 10 elements
                    text_content = await elem.text_content()
                    if text_content:
                        extracted_text.append(text_content.strip())
                result_data["extracted_text"] = extracted_text
                logger.info(f"Extracted {len(extracted_text)} text elements from: {selector}")

            elif action == "screenshot":
                pass  # Just take screenshot below

            else:
                raise ValueError(f"Unknown action: {action}")

            # Take screenshot if requested
            if screenshot:
                screenshot_bytes = await page.screenshot()
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                result_data["screenshot"] = screenshot_b64
                result_data["screenshot_size"] = len(screenshot_bytes)
                logger.info(f"Captured screenshot ({len(screenshot_bytes)} bytes)")

            # Get current URL and title
            result_data["current_url"] = page.url
            result_data["current_title"] = await page.title()

            await browser.close()

            result_data["success"] = True
            logger.info(f"Browser automation completed successfully")

    except Exception as e:
        logger.error(f"Browser automation failed: {e}")
        result_data["error"] = str(e)

    return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result_data, indent=2))])


# Alias for compatibility
simple_browser_automation = browser_automation
