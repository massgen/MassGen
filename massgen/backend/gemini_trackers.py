# -*- coding: utf-8 -*-
"""
MCP tracking utilities for the Gemini backend, handling deduplication across streaming chunks and extraction from SDK objects.
"""

import hashlib
import json
import time
from typing import Any, Dict, Optional


class MCPResponseTracker:
    """
    Tracks MCP tool responses across streaming chunks to handle deduplication.

    Similar to MCPCallTracker but for tracking tool responses to avoid duplicate output.
    """

    def __init__(self):
        """Initialize the tracker with empty storage."""
        self.processed_responses = set()  # Store hashes of processed responses
        self.response_history = []  # Store all unique responses with timestamps

    def get_response_hash(self, tool_name: str, tool_response: Any) -> str:
        """
        Generate a unique hash for a tool response based on name and response content.

        Args:
            tool_name: Name of the tool that responded
            tool_response: Response from the tool

        Returns:
            MD5 hash string identifying this specific response
        """
        # Create a deterministic string representation
        content = f"{tool_name}:{str(tool_response)}"
        return hashlib.md5(content.encode()).hexdigest()

    def is_new_response(self, tool_name: str, tool_response: Any) -> bool:
        """
        Check if this is a new tool response we haven't seen before.

        Args:
            tool_name: Name of the tool that responded
            tool_response: Response from the tool

        Returns:
            True if this is a new response, False if already processed
        """
        response_hash = self.get_response_hash(tool_name, tool_response)
        return response_hash not in self.processed_responses

    def add_response(self, tool_name: str, tool_response: Any) -> Dict[str, Any]:
        """
        Add a new response to the tracker.

        Args:
            tool_name: Name of the tool that responded
            tool_response: Response from the tool

        Returns:
            Dictionary containing response details and timestamp
        """
        response_hash = self.get_response_hash(tool_name, tool_response)
        self.processed_responses.add(response_hash)

        record = {
            "tool_name": tool_name,
            "response": tool_response,
            "hash": response_hash,
            "timestamp": time.time(),
        }
        self.response_history.append(record)
        return record


class MCPCallTracker:
    """
    Tracks MCP tool calls across streaming chunks to handle deduplication.

    Uses hashing to identify unique tool calls and timestamps to track when they occurred.
    This ensures we don't double-count the same tool call appearing in multiple chunks.
    """

    def __init__(self):
        """Initialize the tracker with empty storage."""
        self.processed_calls = set()  # Store hashes of processed calls
        self.call_history = []  # Store all unique calls with timestamps
        self.last_chunk_calls = []  # Track calls from the last chunk for deduplication
        self.dedup_window = 0.5  # Time window in seconds for deduplication

    def get_call_hash(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """
        Generate a unique hash for a tool call based on name and arguments.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool

        Returns:
            MD5 hash string identifying this specific call
        """
        # Create a deterministic string representation
        content = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()

    def is_new_call(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        """
        Check if this is a new tool call we haven't seen before.

        Uses a time-window based approach: identical calls within the dedup_window
        are considered duplicates (likely from streaming chunks), while those outside
        the window are considered new calls (likely intentional repeated calls).

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool

        Returns:
            True if this is a new call, False if we've seen it before
        """
        call_hash = self.get_call_hash(tool_name, tool_args)
        current_time = time.time()

        # Check if this call exists in recent history within the dedup window
        for call in self.call_history[-10:]:  # Check last 10 calls for efficiency
            if call.get("hash") == call_hash:
                time_diff = current_time - call.get("timestamp", 0)
                if time_diff < self.dedup_window:
                    # This is likely a duplicate from streaming chunks
                    return False
                # If outside the window, treat as a new intentional call

        # Mark as processed
        self.processed_calls.add(call_hash)
        return True

    def add_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new tool call to the history.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool

        Returns:
            Dictionary containing the call details with timestamp and hash
        """
        call_record = {
            "name": tool_name,
            "arguments": tool_args,
            "timestamp": time.time(),
            "hash": self.get_call_hash(tool_name, tool_args),
            "sequence": len(self.call_history),  # Add sequence number for ordering
        }
        self.call_history.append(call_record)

        # Clean up old history to prevent memory growth
        if len(self.call_history) > 100:
            self.call_history = self.call_history[-50:]

        return call_record

    def get_summary(self) -> str:
        """
        Get a summary of all tracked tool calls.

        Returns:
            Human-readable summary of tool usage
        """
        if not self.call_history:
            return "No MCP tools called"

        tool_names = [call["name"] for call in self.call_history]
        unique_tools = list(dict.fromkeys(tool_names))  # Preserve order
        return f"Used {len(self.call_history)} MCP tool calls: {', '.join(unique_tools)}"


class MCPResponseExtractor:
    """
    Extracts MCP tool calls and responses from Gemini SDK stream chunks.

    This class parses the internal SDK chunks to capture:
    - function_call parts (tool invocations)
    - function_response parts (tool results)
    - Paired call-response data for tracking complete tool executions
    """

    def __init__(self):
        """Initialize the extractor with empty storage."""
        self.mcp_calls = []  # All tool calls
        self.mcp_responses = []  # All tool responses
        self.call_response_pairs = []  # Matched call-response pairs
        self._pending_call = None  # Track current call awaiting response

    def extract_function_call(self, function_call) -> Optional[Dict[str, Any]]:
        """
        Extract tool call information from SDK function_call object.

        Tries multiple methods to extract data from different SDK versions:
        1. Direct attributes (name, args)
        2. Dictionary-like interface (get method)
        3. __dict__ attributes
        4. Protobuf _pb attributes
        """
        tool_name = None
        tool_args = None

        # Method 1: Direct attributes
        tool_name = getattr(function_call, "name", None)
        tool_args = getattr(function_call, "args", None)

        # Method 2: Dictionary-like object
        if tool_name is None:
            try:
                if hasattr(function_call, "get"):
                    tool_name = function_call.get("name", None)
                    tool_args = function_call.get("args", None)
            except Exception:
                pass

        # Method 3: __dict__ inspection
        if tool_name is None:
            try:
                if hasattr(function_call, "__dict__"):
                    fc_dict = function_call.__dict__
                    tool_name = fc_dict.get("name", None)
                    tool_args = fc_dict.get("args", None)
            except Exception:
                pass

        # Method 4: Protobuf _pb attribute
        if tool_name is None:
            try:
                if hasattr(function_call, "_pb"):
                    pb = function_call._pb
                    if hasattr(pb, "name"):
                        tool_name = pb.name
                    if hasattr(pb, "args"):
                        tool_args = pb.args
            except Exception:
                pass

        if tool_name:
            call_data = {
                "name": tool_name,
                "arguments": tool_args or {},
                "timestamp": time.time(),
                "raw": str(function_call)[:200],  # Truncate for logging
            }
            self.mcp_calls.append(call_data)
            self._pending_call = call_data
            return call_data

        return None

    def extract_function_response(self, function_response) -> Optional[Dict[str, Any]]:
        """
        Extract tool response information from SDK function_response object.

        Uses same extraction methods as function_call for consistency.
        """
        tool_name = None
        tool_response = None

        # Method 1: Direct attributes
        tool_name = getattr(function_response, "name", None)
        tool_response = getattr(function_response, "response", None)

        # Method 2: Dictionary-like object
        if tool_name is None:
            try:
                if hasattr(function_response, "get"):
                    tool_name = function_response.get("name", None)
                    tool_response = function_response.get("response", None)
            except Exception:
                pass

        # Method 3: __dict__ inspection
        if tool_name is None:
            try:
                if hasattr(function_response, "__dict__"):
                    fr_dict = function_response.__dict__
                    tool_name = fr_dict.get("name", None)
                    tool_response = fr_dict.get("response", None)
            except Exception:
                pass

        # Method 4: Protobuf _pb attribute
        if tool_name is None:
            try:
                if hasattr(function_response, "_pb"):
                    pb = function_response._pb
                    if hasattr(pb, "name"):
                        tool_name = pb.name
                    if hasattr(pb, "response"):
                        tool_response = pb.response
            except Exception:
                pass

        if tool_name:
            response_data = {
                "name": tool_name,
                "response": tool_response or {},
                "timestamp": time.time(),
                "raw": str(function_response)[:500],  # Truncate for logging
            }
            self.mcp_responses.append(response_data)

            # Pair with pending call if names match
            if self._pending_call and self._pending_call["name"] == tool_name:
                self.call_response_pairs.append(
                    {
                        "call": self._pending_call,
                        "response": response_data,
                        "duration": response_data["timestamp"] - self._pending_call["timestamp"],
                        "paired_at": time.time(),
                    },
                )
                self._pending_call = None

            return response_data

        return None

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all extracted MCP tool interactions.
        """
        return {
            "total_calls": len(self.mcp_calls),
            "total_responses": len(self.mcp_responses),
            "paired_interactions": len(self.call_response_pairs),
            "pending_call": self._pending_call is not None,
            "tool_names": list(set(call["name"] for call in self.mcp_calls)),
            "average_duration": (sum(pair["duration"] for pair in self.call_response_pairs) / len(self.call_response_pairs) if self.call_response_pairs else 0),
        }

    def clear(self):
        """Clear all stored data."""
        self.mcp_calls.clear()
        self.mcp_responses.clear()
        self.call_response_pairs.clear()
        self._pending_call = None
