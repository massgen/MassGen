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
        self.start_lmstudio_server(**kwargs)

    # Local server usage is typically free; report zero cost
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:  # type: ignore[override]
        return 0.0

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

    def estimate_tokens(self, text: str) -> int:  # type: ignore[override]
        # Simple heuristic consistent with ChatCompletionsBackend
        return int(len(text.split()) * 1.3)

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

        # Start the server (synchronously)
        try:
            # Start LM Studio server
            subprocess.run(["lms", "server", "start"], check=True)

            # Wait a bit for server to start
            time.sleep(2)

            print("LM Studio server started successfully.")
        except Exception as e:
            raise Exception(f"Failed to start LM Studio server: {e}")

        # Ensure specified model is available and loaded
        model_name = kwargs.get("model", "")
        if model_name:
            self._ensure_model_available(model_name)

    def _ensure_model_available(self, model_name: str) -> None:
        """
        Ensure a specific model is downloaded and loaded in LM Studio.to prevent unnecessary reloading of already loaded models.

        Args:
            model_name: Name/key of the model to ensure is available
        """
        # First, ensure model is downloaded locally
        try:
            downloaded_models = lms.list_downloaded_models()
            if model_name not in downloaded_models:
                print(f"Model '{model_name}' not found locally. Downloading...")
                subprocess.run(["lms", "get", model_name], check=True)
                print(f"Model '{model_name}' downloaded successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not check/download model '{model_name}': {e}")
            return

        # Then ensure model is loaded with retry logic
        self._load_model_with_retry(model_name)

    def _load_model_with_retry(self, model_name: str, max_retries: int = 3, retry_delay: int = 2) -> None:
        """
        Load a model with retry logic to handle transient failures.

        Args:
            model_name: Name/key of the model to load
            max_retries: Maximum number of loading attempts
            retry_delay: Delay between retry attempts in seconds
        """
        for attempt in range(max_retries):
            try:
                # Check if model is already loaded before attempting to load it
                loaded_models = lms.list_loaded_models()

                if model_name in loaded_models:
                    print(f"Model '{model_name}' is already loaded and ready.")
                    return
                else:
                    # this prevents reloading already loaded models
                    print(f"Loading model '{model_name}'... (attempt {attempt + 1}/{max_retries})")

                    # Get the model instance - lms.llm() loads only if not already loaded
                    # Setting TTL to 1 hour to prevent premature unloading due to inactivity
                    model = lms.llm(model_name, ttl=3600)

                    print(f"Model '{model_name}' loaded successfully.")
                    return

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Warning: Model loading attempt {attempt + 1} failed: {e}")
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print(f"Error: Could not load model '{model_name}' after {max_retries} attempts: {e}")
                    print("Continuing without explicit model loading - will use whatever is currently loaded.")

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
