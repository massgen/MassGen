from __future__ import annotations

"""
LM Studio backend using an OpenAI-compatible Chat Completions API.

Defaults are tailored for a local LM Studio server:
- base_url: http://localhost:1234/v1
- api_key:  "lm-studio" (LM Studio accepts any non-empty key)

This backend delegates most behavior to ChatCompletionsBackend, only
customizing provider naming, API key resolution, and cost calculation.
"""

from typing import Optional, List, Dict, Any, AsyncGenerator
import subprocess
import shutil
import os
import platform
import json
import time
import lmstudio as lms

from .chat_completions import ChatCompletionsBackend
from .base import StreamChunk


class LMStudioBackend(ChatCompletionsBackend):
    """LM Studio backend (OpenAI-compatible, local server)."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(
            api_key="lm-studio", **kwargs
        )  # Override to avoid environment-variable enforcement; LM Studio accepts any key
        self._models_attempted = (
            set()
        )  # Track models this instance has attempted to load
        self.start_lmstudio_server(**kwargs)

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
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
        # Check if lms CLI is installed
        lms_path = shutil.which("lms")
        if not lms_path:
            print("LM Studio CLI not found. Installing...")
            try:
                # Install LM Studio CLI based on platform
                system = platform.system().lower()
                if system == "darwin":  # macOS
                    subprocess.run(["brew", "install", "lmstudio"], check=True)
                elif system == "linux":
                    # Download and install for Linux
                    subprocess.run(
                        ["curl", "-sSL", "https://lmstudio.ai/install.sh", "|", "sh"],
                        shell=True,
                        check=True,
                    )
                elif system == "windows":
                    # Windows installation via PowerShell
                    subprocess.run(
                        [
                            "powershell",
                            "-Command",
                            "iwr -useb https://lmstudio.ai/install.ps1 | iex",
                        ],
                        check=True,
                    )
                else:
                    raise Exception(f"Unsupported platform: {system}")
            except subprocess.CalledProcessError as e:
                raise Exception(f"Failed to install LM Studio CLI: {e}")

        # Start the server (in background/detached mode)
        try:
            # Start LM Studio server in background
            # Use Popen instead of run to avoid blocking
            process = subprocess.Popen(
                ["lms", "server", "start"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait a bit for server to start
            time.sleep(3)

            # Check if process started successfully
            if process.poll() is None:
                print("LM Studio server started successfully (running in background).")
            else:
                stdout, stderr = process.communicate(timeout=1)
                if stdout:
                    print(f"Server output: {stdout}")
                if stderr:
                    stderr_lower = stderr.lower()
                    if "success" in stderr_lower or "running on port" in stderr_lower:
                        print(f"Server info: {stderr.strip()}")
                    elif "warning" in stderr_lower or "warn" in stderr_lower:
                        print(f"Server warning: {stderr.strip()}")
                    else:
                        print(f"Server error: {stderr.strip()}")
                print("LM Studio server started successfully.")
        except Exception as e:
            raise Exception(f"Failed to start LM Studio server: {e}")

        # Check if model exists locally
        model_name = kwargs.get("model", "")
        if model_name:
            try:
                # List available models using lms list
                downloaded = lms.list_downloaded_models()

                # Check if model is in the list
                model_keys = [m.model_key for m in downloaded]
                if model_name not in model_keys:
                    print(f"Model '{model_name}' not found locally. Downloading...")
                    # Download the model using lms get
                    subprocess.run(["lms", "get", model_name], check=True)
                    print(f"Model '{model_name}' downloaded successfully.")

            except Exception as e:
                print(f"Warning: Could not check/download model: {e}")

            try:
                # Check if this instance already attempted to load this model
                if model_name in self._models_attempted:
                    print(
                        f"Model '{model_name}' load already attempted by this instance."
                    )
                    return

                # Add brief wait to allow model to finish loading after download
                time.sleep(5)

                # List available models using lms list
                loaded = lms.list_loaded_models()

                # Check if model is in the list
                # LLM objects have 'identifier' attribute, not 'model_key'
                loaded_identifiers = [m.identifier for m in loaded]
                if model_name not in loaded_identifiers:
                    print(f"Model '{model_name}' not loaded. Loading...")
                    # Mark model as attempted before loading to prevent race conditions
                    self._models_attempted.add(model_name)
                    # Load the model using lms load
                    subprocess.run(["lms", "load", model_name], check=True)
                    print(f"Model '{model_name}' loaded successfully.")
                else:
                    print(f"Model '{model_name}' is already loaded.")
                    # Mark as attempted since it's already available
                    self._models_attempted.add(model_name)

            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to load model '{model_name}': {e}")
            except Exception as e:
                print(f"Warning: Could not check loaded models: {e}")

    def end_lmstudio_server(self):
        """Stop the LM Studio server after receiving all chunks."""
        try:
            # Use lms server end command as specified in requirement
            result = subprocess.run(
                ["lms", "server", "end"], capture_output=True, text=True
            )

            if result.returncode == 0:
                print("LM Studio server ended successfully.")
            else:
                # Fallback to stop command if end doesn't work
                subprocess.run(["lms", "server", "stop"], check=True)
                print("LM Studio server stopped successfully.")
        except Exception as e:
            print(f"Warning: Failed to end LM Studio server: {e}")
