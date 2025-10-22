# -*- coding: utf-8 -*-
"""
Environment Manager for Computer Use Tool.

This module manages different execution environments (browser, Docker VM, etc.)
and provides a unified interface for executing computer actions.
"""

import asyncio
import subprocess
from abc import ABC, abstractmethod
from typing import Dict, Literal, Optional


class BaseEnvironment(ABC):
    """Base class for all environment implementations."""

    def __init__(self, display_width: int, display_height: int, config: Dict):
        """
        Initialize the environment.

        Args:
            display_width: Screen width in pixels
            display_height: Screen height in pixels
            config: Additional configuration parameters
        """
        self.display_width = display_width
        self.display_height = display_height
        self.config = config

    @abstractmethod
    async def start(self) -> None:
        """Start the environment."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the environment."""
        pass

    @abstractmethod
    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at the specified position."""
        pass

    @abstractmethod
    async def double_click(self, x: int, y: int, button: str = "left") -> None:
        """Double click at the specified position."""
        pass

    @abstractmethod
    async def scroll(
        self, x: int, y: int, scroll_x: int = 0, scroll_y: int = 0
    ) -> None:
        """Scroll at the specified position."""
        pass

    @abstractmethod
    async def press_key(self, key: str) -> None:
        """Press a keyboard key."""
        pass

    @abstractmethod
    async def type_text(self, text: str) -> None:
        """Type text."""
        pass

    @abstractmethod
    async def move_mouse(self, x: int, y: int) -> None:
        """Move mouse to position."""
        pass

    @abstractmethod
    async def get_screenshot(self) -> Optional[bytes]:
        """Get screenshot as bytes."""
        pass


class BrowserEnvironment(BaseEnvironment):
    """Browser environment using Playwright."""

    def __init__(self, display_width: int, display_height: int, config: Dict):
        super().__init__(display_width, display_height, config)
        self.browser = None
        self.page = None
        self.playwright = None
        self._playwright_obj = None

    async def start(self) -> None:
        """Start a browser instance using Playwright."""
        try:
            from playwright.async_api import async_playwright

            self._playwright_obj = await async_playwright().start()
            self.playwright = self._playwright_obj

            # Launch browser with security settings
            self.browser = await self.playwright.chromium.launch(
                headless=self.config.get("headless", False),
                chromium_sandbox=True,
                env={},
                args=[
                    "--disable-extensions",
                    "--disable-file-system",
                ],
            )

            # Create a new page
            self.page = await self.browser.new_page()
            await self.page.set_viewport_size(
                {"width": self.display_width, "height": self.display_height}
            )

            # Navigate to initial URL if provided
            initial_url = self.config.get("initial_url", "https://www.google.com")
            await self.page.goto(initial_url)

        except ImportError:
            raise ImportError(
                "Playwright is required for browser environment. "
                "Install it with: pip install playwright && playwright install"
            )

    async def stop(self) -> None:
        """Stop the browser instance."""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if self._playwright_obj:
            await self._playwright_obj.stop()

    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at the specified position."""
        if self.page:
            await self.page.mouse.click(x, y, button=button)

    async def double_click(self, x: int, y: int, button: str = "left") -> None:
        """Double click at the specified position."""
        if self.page:
            await self.page.mouse.dblclick(x, y, button=button)

    async def scroll(
        self, x: int, y: int, scroll_x: int = 0, scroll_y: int = 0
    ) -> None:
        """Scroll at the specified position."""
        if self.page:
            await self.page.mouse.move(x, y)
            await self.page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")

    async def press_key(self, key: str) -> None:
        """Press a keyboard key."""
        if self.page:
            # Map common key names
            key_map = {
                "ENTER": "Enter",
                "SPACE": " ",
                "TAB": "Tab",
                "BACKSPACE": "Backspace",
                "DELETE": "Delete",
                "ESCAPE": "Escape",
                "ARROWUP": "ArrowUp",
                "ARROWDOWN": "ArrowDown",
                "ARROWLEFT": "ArrowLeft",
                "ARROWRIGHT": "ArrowRight",
            }
            mapped_key = key_map.get(key.upper(), key)
            await self.page.keyboard.press(mapped_key)

    async def type_text(self, text: str) -> None:
        """Type text."""
        if self.page:
            await self.page.keyboard.type(text)

    async def move_mouse(self, x: int, y: int) -> None:
        """Move mouse to position."""
        if self.page:
            await self.page.mouse.move(x, y)

    async def get_screenshot(self) -> Optional[bytes]:
        """Get screenshot as bytes."""
        if self.page:
            return await self.page.screenshot()
        return None


class DockerEnvironment(BaseEnvironment):
    """Docker virtual machine environment."""

    def __init__(self, display_width: int, display_height: int, config: Dict):
        super().__init__(display_width, display_height, config)
        self.container_name = config.get("container_name", "cua-container")
        self.display = config.get("display", ":99")

    async def start(self) -> None:
        """Start Docker container (assumes container is already running)."""
        # Check if container is running
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.container_name}"],
                capture_output=True,
                text=True,
            )
            if not result.stdout.strip():
                raise RuntimeError(
                    f"Docker container '{self.container_name}' is not running. "
                    "Please start it first."
                )
        except FileNotFoundError:
            raise RuntimeError("Docker is not installed or not in PATH")

    async def stop(self) -> None:
        """Stop Docker container (optional, can leave it running)."""
        # By default, we don't stop the container as it might be reused
        pass

    def _docker_exec(self, cmd: str) -> str:
        """Execute a command in the Docker container."""
        safe_cmd = cmd.replace('"', '\\"')
        docker_cmd = f'docker exec {self.container_name} sh -c "{safe_cmd}"'
        result = subprocess.run(docker_cmd, shell=True, capture_output=True)
        return result.stdout.decode("utf-8", errors="ignore")

    def _docker_exec_bytes(self, cmd: str) -> bytes:
        """Execute a command in the Docker container and return bytes."""
        safe_cmd = cmd.replace('"', '\\"')
        docker_cmd = f'docker exec {self.container_name} sh -c "{safe_cmd}"'
        result = subprocess.run(docker_cmd, shell=True, capture_output=True)
        return result.stdout

    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at the specified position using xdotool."""
        button_map = {"left": 1, "middle": 2, "right": 3}
        b = button_map.get(button, 1)
        cmd = f"DISPLAY={self.display} xdotool mousemove {x} {y} click {b}"
        await asyncio.get_event_loop().run_in_executor(None, self._docker_exec, cmd)

    async def double_click(self, x: int, y: int, button: str = "left") -> None:
        """Double click at the specified position using xdotool."""
        button_map = {"left": 1, "middle": 2, "right": 3}
        b = button_map.get(button, 1)
        cmd = f"DISPLAY={self.display} xdotool mousemove {x} {y} click --repeat 2 {b}"
        await asyncio.get_event_loop().run_in_executor(None, self._docker_exec, cmd)

    async def scroll(
        self, x: int, y: int, scroll_x: int = 0, scroll_y: int = 0
    ) -> None:
        """Scroll at the specified position using xdotool."""
        # Move mouse to position
        cmd = f"DISPLAY={self.display} xdotool mousemove {x} {y}"
        await asyncio.get_event_loop().run_in_executor(None, self._docker_exec, cmd)

        # Scroll vertically (button 4 = scroll up, button 5 = scroll down)
        if scroll_y != 0:
            button = 4 if scroll_y < 0 else 5
            clicks = abs(scroll_y)
            for _ in range(clicks):
                cmd = f"DISPLAY={self.display} xdotool click {button}"
                await asyncio.get_event_loop().run_in_executor(
                    None, self._docker_exec, cmd
                )

    async def press_key(self, key: str) -> None:
        """Press a keyboard key using xdotool."""
        # Map common key names to xdotool format
        key_map = {
            "ENTER": "Return",
            "SPACE": "space",
            "TAB": "Tab",
            "BACKSPACE": "BackSpace",
            "DELETE": "Delete",
            "ESCAPE": "Escape",
        }
        mapped_key = key_map.get(key.upper(), key)
        cmd = f"DISPLAY={self.display} xdotool key '{mapped_key}'"
        await asyncio.get_event_loop().run_in_executor(None, self._docker_exec, cmd)

    async def type_text(self, text: str) -> None:
        """Type text using xdotool."""
        cmd = f"DISPLAY={self.display} xdotool type '{text}'"
        await asyncio.get_event_loop().run_in_executor(None, self._docker_exec, cmd)

    async def move_mouse(self, x: int, y: int) -> None:
        """Move mouse to position using xdotool."""
        cmd = f"DISPLAY={self.display} xdotool mousemove {x} {y}"
        await asyncio.get_event_loop().run_in_executor(None, self._docker_exec, cmd)

    async def get_screenshot(self) -> Optional[bytes]:
        """Get screenshot using ImageMagick import command."""
        cmd = f"export DISPLAY={self.display} && import -window root png:-"
        screenshot_bytes = await asyncio.get_event_loop().run_in_executor(
            None, self._docker_exec_bytes, cmd
        )
        return screenshot_bytes


class EnvironmentManager:
    """Manager for different execution environments."""

    def __init__(
        self,
        environment: Literal["browser", "mac", "windows", "ubuntu"],
        display_width: int,
        display_height: int,
        config: Dict,
    ):
        """
        Initialize the environment manager.

        Args:
            environment: Type of environment to use
            display_width: Screen width in pixels
            display_height: Screen height in pixels
            config: Additional configuration parameters
        """
        self.environment_type = environment
        self.display_width = display_width
        self.display_height = display_height
        self.config = config

        # Create appropriate environment
        if environment == "browser":
            self.env = BrowserEnvironment(display_width, display_height, config)
        elif environment in ["mac", "windows", "ubuntu"]:
            # Use Docker environment for OS-level automation
            self.env = DockerEnvironment(display_width, display_height, config)
        else:
            raise ValueError(f"Unsupported environment: {environment}")

    async def start(self) -> None:
        """Start the environment."""
        await self.env.start()

    async def stop(self) -> None:
        """Stop the environment."""
        await self.env.stop()

    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at the specified position."""
        await self.env.click(x, y, button)

    async def double_click(self, x: int, y: int, button: str = "left") -> None:
        """Double click at the specified position."""
        await self.env.double_click(x, y, button)

    async def scroll(
        self, x: int, y: int, scroll_x: int = 0, scroll_y: int = 0
    ) -> None:
        """Scroll at the specified position."""
        await self.env.scroll(x, y, scroll_x, scroll_y)

    async def press_key(self, key: str) -> None:
        """Press a keyboard key."""
        await self.env.press_key(key)

    async def type_text(self, text: str) -> None:
        """Type text."""
        await self.env.type_text(text)

    async def move_mouse(self, x: int, y: int) -> None:
        """Move mouse to position."""
        await self.env.move_mouse(x, y)

    async def get_screenshot(self) -> Optional[bytes]:
        """Get screenshot as bytes."""
        return await self.env.get_screenshot()
