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
from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
)


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
        # Extract agent_id for logging
        agent_id = kwargs.get("agent_id", None)

        log_backend_activity(
            "LM Studio",
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Log messages being sent
        log_backend_agent_message(
            agent_id or "default",
            "SEND",
            {"messages": messages, "tools": len(tools) if tools else 0},
            backend_name="LM Studio",
        )

        # Ensure LM Studio defaults
        base_url = kwargs.get("base_url", "http://localhost:1234/v1")
        kwargs["base_url"] = base_url

        try:
            async for chunk in super().stream_with_tools(messages, tools, **kwargs):
                # Log stream chunks
                if chunk.type == "content" and chunk.content:
                    log_backend_agent_message(
                        agent_id or "default",
                        "RECV",
                        {"content": chunk.content},
                        backend_name="LM Studio",
                    )
                    log_stream_chunk(
                        "backend.lmstudio", "content", chunk.content, agent_id
                    )
                elif chunk.type == "error":
                    log_stream_chunk("backend.lmstudio", "error", chunk.error, agent_id)
                elif chunk.type == "tool_calls":
                    log_stream_chunk(
                        "backend.lmstudio", "tool_calls", chunk.tool_calls, agent_id
                    )
                elif chunk.type == "done":
                    log_stream_chunk("backend.lmstudio", "done", None, agent_id)

                yield chunk
        except Exception as e:
            error_msg = f"LM Studio backend error: {str(e)}"
            log_stream_chunk("backend.lmstudio", "error", error_msg, agent_id)
            yield StreamChunk(type="error", error=error_msg)

        # self.end_lmstudio_server()

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "LM Studio"

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

        # Check if model exists locally
        model_name = kwargs.get("model", "")
        if model_name:
            try:
                # List available models using lms list
                downloaded = lms.list_downloaded_models()

                # Check if model is in the list
                if model_name not in downloaded:
                    print(f"Model '{model_name}' not found locally. Downloading...")
                    # Download the model using lms get
                    subprocess.run(["lms", "get", model_name], check=True)
                    print(f"Model '{model_name}' downloaded successfully.")

            except subprocess.CalledProcessError as e:
                print(f"Warning: Could not check/download/load model: {e}")

            try:
                # List available models using lms list
                loaded = lms.list_loaded_models()

                # Check if model is in the list
                if model_name not in loaded:
                    print(f"Model '{model_name}' not loaded. Loading...")
                    # Download the model using lms get
                    subprocess.run(["lms", "load", model_name], check=True)
                    print(f"Model '{model_name}' loaded successfully.")

            except subprocess.CalledProcessError as e:
                print(f"Warning: Could not check/download/load model: {e}")

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
