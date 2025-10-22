# -*- coding: utf-8 -*-
"""
Action Handlers for Computer Use Tool.

This module provides handlers for different computer actions like click, type, scroll, etc.
Each action is executed on the appropriate environment (browser, Docker VM, etc.).
"""

import asyncio
from typing import Any, Dict


class ActionHandler:
    """Handles execution of computer actions on different environments."""

    def __init__(self, environment_manager):
        """
        Initialize the action handler.

        Args:
            environment_manager: The environment manager instance to execute actions on
        """
        self.env_manager = environment_manager

    async def execute_action(self, action: Dict[str, Any]) -> None:
        """
        Execute a computer action based on its type.

        Args:
            action: Dictionary containing action type and parameters

        Raises:
            ValueError: If action type is not supported
        """
        action_type = action.get("type")

        if action_type == "click":
            await self._handle_click(action)
        elif action_type == "double_click":
            await self._handle_double_click(action)
        elif action_type == "scroll":
            await self._handle_scroll(action)
        elif action_type == "keypress":
            await self._handle_keypress(action)
        elif action_type == "type":
            await self._handle_type(action)
        elif action_type == "wait":
            await self._handle_wait(action)
        elif action_type == "screenshot":
            await self._handle_screenshot(action)
        elif action_type == "move_mouse":
            await self._handle_move_mouse(action)
        else:
            raise ValueError(f"Unsupported action type: {action_type}")

    async def _handle_click(self, action: Dict[str, Any]) -> None:
        """
        Handle click action.

        Args:
            action: Click action parameters (x, y, button)
        """
        x = action.get("x")
        y = action.get("y")
        button = action.get("button", "left")

        await self.env_manager.click(x, y, button)

    async def _handle_double_click(self, action: Dict[str, Any]) -> None:
        """
        Handle double click action.

        Args:
            action: Double click action parameters (x, y, button)
        """
        x = action.get("x")
        y = action.get("y")
        button = action.get("button", "left")

        await self.env_manager.double_click(x, y, button)

    async def _handle_scroll(self, action: Dict[str, Any]) -> None:
        """
        Handle scroll action.

        Args:
            action: Scroll action parameters (x, y, scroll_x, scroll_y)
        """
        x = action.get("x")
        y = action.get("y")
        scroll_x = action.get("scroll_x", 0)
        scroll_y = action.get("scroll_y", 0)

        await self.env_manager.scroll(x, y, scroll_x, scroll_y)

    async def _handle_keypress(self, action: Dict[str, Any]) -> None:
        """
        Handle keypress action.

        Args:
            action: Keypress action parameters (keys)
        """
        keys = action.get("keys", [])

        for key in keys:
            await self.env_manager.press_key(key)

    async def _handle_type(self, action: Dict[str, Any]) -> None:
        """
        Handle type action (typing text).

        Args:
            action: Type action parameters (text)
        """
        text = action.get("text", "")

        await self.env_manager.type_text(text)

    async def _handle_wait(self, action: Dict[str, Any]) -> None:
        """
        Handle wait action.

        Args:
            action: Wait action parameters (duration)
        """
        duration = action.get("duration", 2.0)
        await self.wait(duration)

    async def _handle_screenshot(self, action: Dict[str, Any]) -> None:
        """
        Handle screenshot action.

        Args:
            action: Screenshot action parameters
        """
        # Screenshot is typically handled automatically in the main loop
        # This is a no-op action
        pass

    async def _handle_move_mouse(self, action: Dict[str, Any]) -> None:
        """
        Handle move mouse action.

        Args:
            action: Move mouse action parameters (x, y)
        """
        x = action.get("x")
        y = action.get("y")

        await self.env_manager.move_mouse(x, y)

    async def wait(self, duration: float) -> None:
        """
        Wait for a specified duration.

        Args:
            duration: Time to wait in seconds
        """
        await asyncio.sleep(duration)
