# -*- coding: utf-8 -*-
"""
LM Studio backend using an OpenAI-compatible Chat Completions API.

Defaults are tailored for a local LM Studio server:
- base_url: http://localhost:1234/v1
- api_key:  "lm-studio" (LM Studio accepts any non-empty key)

This backend delegates most behavior to ChatCompletionsBackend, only
customizing provider naming, API key resolution, and cost calculation.
"""
# -*- coding: utf-8 -*-
from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import lmstudio as lms

from .base import StreamChunk
from .chat_completions import ChatCompletionsBackend


class LMStudioBackend(ChatCompletionsBackend):
    """LM Studio backend (OpenAI-compatible, local server)."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key="lm-studio", **kwargs)  # Override to avoid environment-variable enforcement; LM Studio accepts any key
        self._models_attempted = set()  # Track models this instance has attempted to load
        self.start_lmstudio_server(**kwargs)

    async def stream_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI-compatible Chat Completions API.

        LM Studio does not require special message conversions; this delegates to
        the generic ChatCompletions implementation while preserving our defaults.
        """

        # Ensure LM Studio defaults
        base_url = kwargs.get("base_url", "http://localhost:1234/v1")
        kwargs["base_url"] = base_url

        async for chunk in super().stream_with_tools(messages, tools, **kwargs):
            yield chunk

        # self.end_lmstudio_server()

    def get_supported_builtin_tools(self) -> List[str]:  # type: ignore[override]
        # LM Studio (local OpenAI-compatible) does not provide provider-builtins
        return []

    def start_lmstudio_server(self, **kwargs):
        """Start LM Studio server after checking CLI and model availability."""
        self._ensure_cli_installed()
        self._start_server()
        model_name = kwargs.get("model", "")
        if model_name:
            self._handle_model(model_name)

    def _ensure_cli_installed(self):
        """Ensure LM Studio CLI is installed."""
        if shutil.which("lms"):
            return
        print("LM Studio CLI not found. Installing...")
        try:
            system = platform.system().lower()
            install_commands = {
                "darwin": (["brew", "install", "lmstudio"], False),
                "linux": (["curl", "-sSL", "https://lmstudio.ai/install.sh", "|", "sh"], True),
                "windows": (["powershell", "-Command", "iwr -useb https://lmstudio.ai/install.ps1 | iex"], False),
            }
            if system not in install_commands:
                raise RuntimeError(f"Unsupported platform: {system}")
            cmd, use_shell = install_commands[system]
            subprocess.run(cmd, shell=use_shell, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to install LM Studio CLI: {e}") from e

    def _start_server(self):
        """Start the LM Studio server in background mode."""
        try:
            with subprocess.Popen(
                ["lms", "server", "start"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ) as process:
                time.sleep(3)
                if process.poll() is None:
                    print("LM Studio server started successfully (running in background).")
                else:
                    self._handle_server_output(process)
        except Exception as e:
            raise RuntimeError(f"Failed to start LM Studio server: {e}") from e

    def _handle_server_output(self, process):
        """Handle server process output."""
        stdout, stderr = process.communicate(timeout=1)
        if stdout:
            print(f"Server output: {stdout}")
        if stderr:
            self._process_stderr(stderr)
        print("LM Studio server started successfully.")

    def _process_stderr(self, stderr):
        """Process server stderr output."""
        stderr_lower = stderr.lower()
        if "success" in stderr_lower or "running on port" in stderr_lower:
            print(f"Server info: {stderr.strip()}")
        elif "warning" in stderr_lower or "warn" in stderr_lower:
            print(f"Server warning: {stderr.strip()}")
        else:
            print(f"Server error: {stderr.strip()}")

    def _handle_model(self, model_name):
        """Handle model downloading and loading."""
        self._ensure_model_downloaded(model_name)
        self._load_model_if_needed(model_name)

    def _ensure_model_downloaded(self, model_name):
        """Ensure model is downloaded locally."""
        try:
            downloaded = lms.list_downloaded_models()
            model_keys = [m.model_key for m in downloaded]
            if model_name not in model_keys:
                print(f"Model '{model_name}' not found locally. Downloading...")
                subprocess.run(["lms", "get", model_name], check=True)
                print(f"Model '{model_name}' downloaded successfully.")
        except Exception as e:
            print(f"Warning: Could not check/download model: {e}")

    def _load_model_if_needed(self, model_name):
        """Load model if not already loaded."""
        try:
            if model_name in self._models_attempted:
                print(f"Model '{model_name}' load already attempted by this instance.")
                return

            time.sleep(5)
            loaded = lms.list_loaded_models()
            loaded_identifiers = [m.identifier for m in loaded]
            if model_name not in loaded_identifiers:
                print(f"Model '{model_name}' not loaded. Loading...")
                self._models_attempted.add(model_name)
                subprocess.run(["lms", "load", model_name], check=True)
                print(f"Model '{model_name}' loaded successfully.")
            else:
                print(f"Model '{model_name}' is already loaded.")
                self._models_attempted.add(model_name)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to load model '{model_name}': {e}")
        except Exception as e:
            print(f"Warning: Could not check loaded models: {e}")

    def end_lmstudio_server(self):
        """Stop the LM Studio server after receiving all chunks."""
        try:
            # Use lms server end command as specified in requirement
            result = subprocess.run(["lms", "server", "end"], capture_output=True, text=True, check=False)

            if result.returncode == 0:
                print("LM Studio server ended successfully.")
            else:
                # Fallback to stop command if end doesn't work
                subprocess.run(["lms", "server", "stop"], check=True)
                print("LM Studio server stopped successfully.")
        except Exception as e:
            print(f"Warning: Failed to end LM Studio server: {e}")
