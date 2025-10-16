# -*- coding: utf-8 -*-
"""
Claude backend implementation using Anthropic's Messages API.
Production-ready implementation with full multi-tool support.

✅ FEATURES IMPLEMENTED:
- ✅ Messages API integration with streaming support
- ✅ Multi-tool support (server-side + user-defined tools combined)
- ✅ Web search tool integration with pricing tracking
- ✅ Code execution tool integration with session management
- ✅ Tool message format conversion for MassGen compatibility
- ✅ Advanced streaming with tool parameter streaming
- ✅ Error handling and token usage tracking
- ✅ Production-ready pricing calculations (2025 rates)

Multi-Tool Capabilities:
- Can combine web search + code execution + user functions in single request
- No API limitations unlike other providers
- Parallel and sequential tool execution supported
- Perfect integration with MassGen StreamChunk pattern
"""
from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

import anthropic
import httpx

from ..api_params_handler import ClaudeAPIParamsHandler
from ..formatter import ClaudeFormatter
from ..logger_config import log_backend_agent_message, log_stream_chunk, logger
from ..mcp_tools.backend_utils import MCPErrorHandler
from .base import FilesystemSupport, StreamChunk
from .base_with_custom_tool_and_mcp import CustomToolAndMCPBackend, UploadFileError


class ClaudeBackend(CustomToolAndMCPBackend):
    """Claude backend using Anthropic's Messages API with full multi-tool support."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.search_count = 0  # Track web search usage for pricing
        self.code_session_hours = 0.0  # Track code execution usage
        self.formatter = ClaudeFormatter()
        self.api_params_handler = ClaudeAPIParamsHandler(self)
        self._uploaded_file_ids: List[str] = []

    def supports_upload_files(self) -> bool:
        """Claude Vision supports inline images; Files API handles PDFs and text docs."""

        return True

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Override to ensure Files API cleanup happens after streaming completes."""
        try:
            async for chunk in super().stream_with_tools(messages, tools, **kwargs):
                yield chunk
        finally:
            await self._cleanup_files_api_resources(**kwargs)

    async def _process_upload_files(
        self,
        messages: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Convert upload_files entries into Claude-compatible multimodal content."""

        processed_messages = await super()._process_upload_files(messages, all_params)
        if not processed_messages:
            return processed_messages

        allowed_mime_types = {
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
        }
        max_image_size_bytes = 5 * 1024 * 1024

        for message in processed_messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue

            converted_items: List[Dict[str, Any]] = []
            for item in content:
                if not isinstance(item, dict):
                    converted_items.append(item)
                    continue

                item_type = item.get("type")
                if item_type == "file_pending_upload":
                    converted_items.append(item)
                    continue

                if item_type != "image":
                    converted_items.append(item)
                    continue

                if "source" in item and isinstance(item["source"], dict):
                    converted_items.append(item)
                    continue

                # Handle base64-encoded images
                if "base64" in item:
                    mime_type = (item.get("mime_type") or "").lower()
                    if mime_type not in allowed_mime_types:
                        raise UploadFileError(
                            f"Unsupported Claude image MIME type: {mime_type or 'unknown'}",
                        )

                    try:
                        decoded = base64.b64decode(item["base64"], validate=True)
                    except binascii.Error as exc:
                        raise UploadFileError("Invalid base64 image data") from exc

                    if len(decoded) > max_image_size_bytes:
                        raise UploadFileError(
                            "Claude Vision image exceeds 5MB size limit",
                        )

                    converted_item = {key: value for key, value in item.items() if key not in {"base64", "mime_type"}}
                    converted_item["type"] = "image"
                    converted_item["source"] = {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": item["base64"],
                    }
                    logger.debug(
                        "Converted base64 image for Claude Vision: %s",
                        converted_item.get("source_path", "inline"),
                    )
                    converted_items.append(converted_item)
                    continue

                # Handle URL-referenced images
                if "url" in item:
                    converted_item = {key: value for key, value in item.items() if key != "url"}
                    converted_item["type"] = "image"
                    converted_item["source"] = {
                        "type": "url",
                        "url": item["url"],
                    }
                    logger.debug(
                        "Converted URL image for Claude Vision: %s",
                        item["url"],
                    )
                    converted_items.append(converted_item)
                    continue

                # Handle Files API references
                if "file_id" in item:
                    converted_item = {key: value for key, value in item.items() if key != "file_id"}
                    converted_item["type"] = "image"
                    converted_item["source"] = {
                        "type": "file",
                        "file_id": item["file_id"],
                    }
                    logger.debug(
                        "Attached Claude file_id reference for image: %s",
                        item["file_id"],
                    )
                    converted_items.append(converted_item)
                    continue

                converted_items.append(item)

            message["content"] = converted_items

        return processed_messages

    async def _upload_files_via_files_api(
        self,
        messages: List[Dict[str, Any]],
        client,
        agent_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Upload files via Claude Files API and replace pending markers with document blocks.

        Claude Files API only supports PDF and TXT files. Unsupported files are gracefully
        skipped and replaced with informative text notes to maintain workflow continuity.
        """
        # Claude Files API only supports PDF and TXT files
        CLAUDE_FILES_API_SUPPORTED_EXTENSIONS = {".pdf", ".txt"}
        CLAUDE_FILES_API_SUPPORTED_MIME_TYPES = {
            "application/pdf",
            "text/plain",
            "text/txt",
        }

        # Find all file_pending_upload markers
        file_locations: List[Tuple[int, int]] = []
        for msg_idx, message in enumerate(messages):
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item_idx, item in enumerate(content):
                if isinstance(item, dict) and item.get("type") == "file_pending_upload":
                    file_locations.append((msg_idx, item_idx))

        if not file_locations:
            return messages

        httpx_client = None
        try:
            httpx_client = httpx.AsyncClient()

            # Track uploaded file IDs, skipped files, failed uploads, and their corresponding locations
            uploaded_files: List[Tuple[int, int, str]] = []  # (msg_idx, item_idx, file_id)
            skipped_files: List[Tuple[int, int, str, str]] = []  # (msg_idx, item_idx, filename, reason)
            failed_uploads: List[Tuple[int, int, str, str]] = []  # (msg_idx, item_idx, filename, reason)

            for msg_idx, item_idx in file_locations:
                marker = messages[msg_idx]["content"][item_idx]
                source = marker.get("source")
                file_path = marker.get("path")
                url = marker.get("url")
                mime_type = marker.get("mime_type", "application/octet-stream")
                filename_hint = marker.get("filename") or marker.get("name")

                # Validate file extension and MIME type for Claude Files API
                file_ext = None
                filename = None

                if source == "local" and file_path:
                    file_ext = Path(file_path).suffix.lower()
                    filename = Path(file_path).name
                    # Re-validate MIME type using mimetypes module for accuracy
                    guessed_mime, _ = mimetypes.guess_type(file_path)
                    if guessed_mime:
                        mime_type = guessed_mime
                elif source == "url" and url:
                    # Extract extension from URL (strip query parameters and fragments)
                    url_path = url.split("?")[0].split("#")[0]
                    file_ext = Path(url_path).suffix.lower()
                    filename = Path(url_path).name or url
                    if not filename_hint:
                        filename_hint = filename
                    # Re-validate MIME type using mimetypes module
                    guessed_mime, _ = mimetypes.guess_type(url_path)
                    if guessed_mime:
                        mime_type = guessed_mime

                # Check if file type is supported (both extension and MIME type)
                is_supported = False
                skip_reason = None

                if file_ext and file_ext.lower() in CLAUDE_FILES_API_SUPPORTED_EXTENSIONS:
                    # Extension is supported, now check MIME type
                    if mime_type and mime_type.lower() in CLAUDE_FILES_API_SUPPORTED_MIME_TYPES:
                        is_supported = True
                    else:
                        skip_reason = f"MIME type '{mime_type}' not supported (extension {file_ext} is valid)"
                else:
                    skip_reason = f"File extension '{file_ext or 'unknown'}' not supported"

                # If file is not supported, skip it gracefully and log warning
                if not is_supported:
                    logger.warning(
                        f"[Agent {agent_id or 'default'}] Skipping unsupported file for Claude Files API: "
                        f"{filename or file_path or url} - {skip_reason}. "
                        f"Only PDF and TXT files are supported.",
                    )
                    skipped_files.append((msg_idx, item_idx, filename or file_path or url or "unknown", skip_reason))
                    continue

                try:
                    if source == "local" and file_path:
                        # Upload local file
                        path_obj = Path(file_path)
                        filename = path_obj.name
                        with open(file_path, "rb") as f:
                            file_bytes = f.read()

                        uploaded_file = await client.beta.files.upload(
                            file=(filename, file_bytes, mime_type),
                        )
                        file_id = getattr(uploaded_file, "id", None)
                        if file_id:
                            self._uploaded_file_ids.append(file_id)
                            uploaded_files.append((msg_idx, item_idx, file_id))
                            logger.info(
                                f"[Agent {agent_id or 'default'}] Uploaded local file via Files API: {filename} -> {file_id}",
                            )
                        else:
                            failure_reason = "Claude Files API response missing file_id"
                            failed_uploads.append(
                                (
                                    msg_idx,
                                    item_idx,
                                    filename or filename_hint or file_path or "unknown",
                                    failure_reason,
                                ),
                            )
                            logger.warning(
                                f"[Agent {agent_id or 'default'}] Failed to upload file via Files API: {failure_reason}",
                            )

                    elif source == "url" and url:
                        # Download and upload URL file
                        response = await httpx_client.get(url, timeout=30.0)
                        response.raise_for_status()

                        # Enforce Claude Files API 500 MB size limit
                        max_size_bytes = 500 * 1024 * 1024  # 500 MB
                        content_length = response.headers.get("Content-Length")
                        if content_length:
                            file_size = int(content_length)
                            if file_size > max_size_bytes:
                                raise UploadFileError(
                                    f"File size {file_size / (1024 * 1024):.2f} MB exceeds Claude Files API limit of 500 MB",
                                )

                        file_bytes = response.content

                        # Cap bytes read if Content-Length was missing
                        if len(file_bytes) > max_size_bytes:
                            raise UploadFileError(
                                f"Downloaded file size {len(file_bytes) / (1024 * 1024):.2f} MB exceeds Claude Files API limit of 500 MB",
                            )

                        filename = url.split("/")[-1] or "document"

                        uploaded_file = await client.beta.files.upload(
                            file=(filename, file_bytes, mime_type),
                        )
                        file_id = getattr(uploaded_file, "id", None)
                        if file_id:
                            self._uploaded_file_ids.append(file_id)
                            uploaded_files.append((msg_idx, item_idx, file_id))
                            logger.info(
                                f"[Agent {agent_id or 'default'}] Uploaded URL file via Files API: {url} -> {file_id}",
                            )
                        else:
                            failure_reason = "Claude Files API response missing file_id"
                            failed_uploads.append(
                                (
                                    msg_idx,
                                    item_idx,
                                    filename or filename_hint or url or "unknown",
                                    failure_reason,
                                ),
                            )
                            logger.warning(
                                f"[Agent {agent_id or 'default'}] Failed to upload file via Files API: {failure_reason}",
                            )

                except Exception as upload_error:
                    logger.warning(
                        f"[Agent {agent_id or 'default'}] Failed to upload file via Files API: {upload_error}",
                    )
                    failure_context = filename or filename_hint or file_path or url or "unknown"
                    failed_uploads.append((msg_idx, item_idx, failure_context, str(upload_error)))
                    continue

        except Exception as e:
            logger.warning(f"[Agent {agent_id or 'default'}] Files API upload error: {e}")
            raise UploadFileError(f"Files API upload failed: {e}") from e
        finally:
            if httpx_client:
                await httpx_client.aclose()

        # Clone messages and replace markers with document blocks or text notes
        updated_messages = [msg.copy() for msg in messages]

        # Replace successfully uploaded files with document blocks
        for msg_idx, item_idx, file_id in reversed(uploaded_files):
            content = updated_messages[msg_idx]["content"]
            if isinstance(content, list):
                # Create document block
                document_block = {
                    "type": "document",
                    "source": {
                        "type": "file",
                        "file_id": file_id,
                    },
                }
                # Replace marker with document block
                new_content = content[:item_idx] + [document_block] + content[item_idx + 1 :]
                updated_messages[msg_idx]["content"] = new_content

        # Replace skipped files with informative text notes
        for msg_idx, item_idx, filename, reason in reversed(skipped_files):
            content = updated_messages[msg_idx]["content"]
            if isinstance(content, list):
                # Create text note explaining the limitation
                text_note = {
                    "type": "text",
                    "text": (f"\n[Note: File '{filename}' was not uploaded to Claude Files API. " f"Reason: {reason}. " f"Claude Files API only supports PDF and TXT files.]\n"),
                }
                # Replace marker with text note
                new_content = content[:item_idx] + [text_note] + content[item_idx + 1 :]
                updated_messages[msg_idx]["content"] = new_content

        # Replace failed uploads with informative text notes
        for msg_idx, item_idx, filename, reason in reversed(failed_uploads):
            content = updated_messages[msg_idx]["content"]
            if isinstance(content, list):
                text_note = {
                    "type": "text",
                    "text": (f"\n[Note: File '{filename}' failed to upload to Claude Files API. " f"Reason: {reason}.]\n"),
                }
                new_content = content[:item_idx] + [text_note] + content[item_idx + 1 :]
                updated_messages[msg_idx]["content"] = new_content

        # Final sweep to ensure all file_pending_upload markers were replaced
        self._ensure_no_pending_upload_markers(updated_messages)

        return updated_messages

    async def _cleanup_files_api_resources(self, **kwargs) -> None:
        """Clean up uploaded files via Files API."""
        if not self._uploaded_file_ids:
            return

        agent_id = kwargs.get("agent_id")
        logger.info(
            f"[Agent {agent_id or 'default'}] Cleaning up {len(self._uploaded_file_ids)} Files API resources...",
        )

        client = None
        try:
            client = self._create_client(**kwargs)

            for file_id in self._uploaded_file_ids:
                try:
                    await client.beta.files.delete(file_id)
                    logger.debug(f"[Agent {agent_id or 'default'}] Deleted Files API file: {file_id}")
                except Exception as delete_error:
                    logger.warning(
                        f"[Agent {agent_id or 'default'}] Failed to delete Files API file {file_id}: {delete_error}",
                    )
                    continue

            self._uploaded_file_ids.clear()
            logger.info(f"[Agent {agent_id or 'default'}] Files API cleanup completed")

        except Exception as e:
            logger.warning(f"[Agent {agent_id or 'default'}] Files API cleanup error: {e}")
        finally:
            if client and hasattr(client, "aclose"):
                await client.aclose()

    def _ensure_no_pending_upload_markers(self, messages: List[Dict[str, Any]]) -> None:
        """Raise UploadFileError if any file_pending_upload markers remain."""
        if not messages:
            return

        for msg_idx, message in enumerate(messages):
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item_idx, item in enumerate(content):
                if isinstance(item, dict) and item.get("type") == "file_pending_upload":
                    identifier = item.get("filename") or item.get("name") or item.get("path") or item.get("url") or "unknown"
                    raise UploadFileError(
                        "Claude Files API upload left unresolved file_pending_upload marker " f"(message {msg_idx}, item {item_idx}, source {identifier}).",
                    )

    async def _stream_without_custom_and_mcp_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Override to integrate Files API uploads into non-MCP streaming."""
        agent_id = kwargs.get("agent_id", None)
        all_params = {**self.config, **kwargs}
        processed_messages = await self._process_upload_files(messages, all_params)

        # Check if we need to upload files via Files API
        if all_params.get("_has_file_search_files"):
            logger.info("Processing Files API uploads...")
            processed_messages = await self._upload_files_via_files_api(processed_messages, client, agent_id)
            all_params["_has_files_api_files"] = True
            all_params.pop("_has_file_search_files", None)

        self._ensure_no_pending_upload_markers(processed_messages)

        api_params = await self.api_params_handler.build_api_params(processed_messages, tools, all_params)

        # Remove any MCP tools from the tools list
        if "tools" in api_params:
            non_mcp_tools = []
            for tool in api_params.get("tools", []):
                # Check different formats for MCP tools
                if tool.get("type") == "function":
                    name = tool.get("function", {}).get("name") if "function" in tool else tool.get("name")
                    if name and name in self._mcp_function_names:
                        continue
                    if name and name in self._custom_tool_names:
                        continue
                elif tool.get("type") == "mcp":
                    continue
                non_mcp_tools.append(tool)
            if non_mcp_tools:
                api_params["tools"] = non_mcp_tools
            else:
                api_params.pop("tools", None)

        # Create stream (handle betas)
        if "betas" in api_params:
            stream = await client.beta.messages.create(**api_params)
        else:
            stream = await client.messages.create(**api_params)

        # Process stream chunks
        async for chunk in self._process_stream(stream, all_params, agent_id):
            yield chunk

    async def _stream_with_custom_and_mcp_tools(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream responses, executing MCP and custom tool function calls when detected."""

        # Build API params for this iteration
        all_params = {**self.config, **kwargs}

        # Check if we need to upload files via Files API
        if all_params.get("_has_file_search_files"):
            logger.info("Processing Files API uploads in MCP mode...")
            agent_id = kwargs.get("agent_id")
            current_messages = await self._upload_files_via_files_api(current_messages, client, agent_id)
            all_params["_has_files_api_files"] = True
            all_params.pop("_has_file_search_files", None)

        self._ensure_no_pending_upload_markers(current_messages)

        api_params = await self.api_params_handler.build_api_params(current_messages, tools, all_params)

        agent_id = kwargs.get("agent_id", None)

        # Create stream (handle code execution beta)
        if "betas" in api_params:
            stream = await client.beta.messages.create(**api_params)
        else:
            stream = await client.messages.create(**api_params)

        content = ""
        current_tool_uses: Dict[str, Dict[str, Any]] = {}
        mcp_tool_calls: List[Dict[str, Any]] = []
        custom_tool_calls: List[Dict[str, Any]] = []
        response_completed = False

        async for event in stream:
            try:
                if event.type == "message_start":
                    continue
                elif event.type == "content_block_start":
                    if hasattr(event, "content_block"):
                        if event.content_block.type == "tool_use":
                            tool_id = event.content_block.id
                            tool_name = event.content_block.name
                            current_tool_uses[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(event, "index", None),
                            }
                        elif event.content_block.type == "server_tool_use":
                            tool_id = event.content_block.id
                            tool_name = event.content_block.name
                            current_tool_uses[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(event, "index", None),
                                "server_side": True,
                            }
                            if tool_name == "code_execution":
                                yield StreamChunk(
                                    type="content",
                                    content="\n💻 [Code Execution] Starting...\n",
                                )
                            elif tool_name == "web_search":
                                yield StreamChunk(
                                    type="content",
                                    content="\n🔍 [Web Search] Starting search...\n",
                                )
                        elif event.content_block.type == "code_execution_tool_result":
                            result_block = event.content_block
                            result_parts = []
                            if hasattr(result_block, "stdout") and result_block.stdout:
                                result_parts.append(f"Output: {result_block.stdout.strip()}")
                            if hasattr(result_block, "stderr") and result_block.stderr:
                                result_parts.append(f"Error: {result_block.stderr.strip()}")
                            if hasattr(result_block, "return_code") and result_block.return_code != 0:
                                result_parts.append(f"Exit code: {result_block.return_code}")
                            if result_parts:
                                result_text = f"\n💻 [Code Execution Result]\n{chr(10).join(result_parts)}\n"
                                yield StreamChunk(type="content", content=result_text)
                elif event.type == "content_block_delta":
                    if hasattr(event, "delta"):
                        if event.delta.type == "text_delta":
                            text_chunk = event.delta.text
                            content += text_chunk
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": text_chunk},
                                backend_name="claude",
                            )
                            log_stream_chunk("backend.claude", "content", text_chunk, agent_id)
                            yield StreamChunk(type="content", content=text_chunk)
                        elif event.delta.type == "input_json_delta":
                            if hasattr(event, "index"):
                                for tool_id, tool_data in current_tool_uses.items():
                                    if tool_data.get("index") == event.index:
                                        partial_json = getattr(event.delta, "partial_json", "")
                                        tool_data["input"] += partial_json
                                        break
                elif event.type == "content_block_stop":
                    if hasattr(event, "index"):
                        for tool_id, tool_data in current_tool_uses.items():
                            if tool_data.get("index") == event.index and tool_data.get("server_side"):
                                tool_name = tool_data.get("name", "")
                                tool_input = tool_data.get("input", "")
                                try:
                                    parsed_input = json.loads(tool_input) if tool_input else {}
                                except json.JSONDecodeError:
                                    parsed_input = {"raw_input": tool_input}
                                if tool_name == "code_execution":
                                    code = parsed_input.get("code", "")
                                    if code:
                                        yield StreamChunk(type="content", content=f"💻 [Code] {code}\n")
                                    yield StreamChunk(
                                        type="content",
                                        content="✅ [Code Execution] Completed\n",
                                    )
                                elif tool_name == "web_search":
                                    query = parsed_input.get("query", "")
                                    if query:
                                        yield StreamChunk(
                                            type="content",
                                            content=f"🔍 [Query] '{query}'\n",
                                        )
                                    yield StreamChunk(
                                        type="content",
                                        content="✅ [Web Search] Completed\n",
                                    )
                                tool_data["processed"] = True
                                break
                elif event.type == "message_delta":
                    pass
                elif event.type == "message_stop":
                    # Identify MCP, custom, and non-MCP/non-custom tool calls among current_tool_uses
                    non_mcp_non_custom_tool_calls = []
                    if current_tool_uses:
                        for tool_use in current_tool_uses.values():
                            tool_name = tool_use.get("name", "")
                            is_server_side = tool_use.get("server_side", False)
                            if is_server_side:
                                continue
                            # Parse accumulated JSON input for tool
                            tool_input = tool_use.get("input", "")
                            try:
                                parsed_input = json.loads(tool_input) if tool_input else {}
                            except json.JSONDecodeError:
                                parsed_input = {"raw_input": tool_input}

                            if self.is_mcp_tool_call(tool_name):
                                mcp_tool_calls.append(
                                    {
                                        "id": tool_use["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": parsed_input,
                                        },
                                    },
                                )
                            elif self.is_custom_tool_call(tool_name):
                                custom_tool_calls.append(
                                    {
                                        "id": tool_use["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": parsed_input,
                                        },
                                    },
                                )
                            else:
                                non_mcp_non_custom_tool_calls.append(
                                    {
                                        "id": tool_use["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": parsed_input,
                                        },
                                    },
                                )
                    # Emit non-MCP/non-custom tool calls for the caller to execute
                    if non_mcp_non_custom_tool_calls:
                        log_stream_chunk("backend.claude", "tool_calls", non_mcp_non_custom_tool_calls, agent_id)
                        yield StreamChunk(type="tool_calls", tool_calls=non_mcp_non_custom_tool_calls)
                    response_completed = True
                    break
            except Exception as event_error:
                error_msg = f"Event processing error: {event_error}"
                log_stream_chunk("backend.claude", "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

        # If we captured MCP or custom tool calls, execute them and recurse
        if response_completed and (mcp_tool_calls or custom_tool_calls):
            # Circuit breaker pre-execution check using base class method
            if not await self._check_circuit_breaker_before_execution():
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_blocked",
                    content="⚠️ [MCP] All servers blocked by circuit breaker",
                    source="circuit_breaker",
                )
                yield StreamChunk(type="done")
                return

            updated_messages = current_messages.copy()

            # Build assistant message with tool_use blocks for all MCP and custom tool calls
            assistant_content = []
            if content:  # Add text content if any
                assistant_content.append({"type": "text", "text": content})

            # Add tool_use blocks for MCP tools
            for tool_call in mcp_tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = tool_call["function"]["arguments"]
                tool_id = tool_call["id"]

                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_args,
                    },
                )

            # Add tool_use blocks for custom tools
            for tool_call in custom_tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = tool_call["function"]["arguments"]
                tool_id = tool_call["id"]

                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_args,
                    },
                )

            # Append the assistant message with tool uses
            updated_messages.append({"role": "assistant", "content": assistant_content})

            # First execute custom tool calls and append results
            for tool_call in custom_tool_calls:
                function_name = tool_call["function"]["name"]

                # Yield custom tool call status
                yield StreamChunk(
                    type="custom_tool_status",
                    status="custom_tool_called",
                    content=f"🔧 [Custom Tool] Calling {function_name}...",
                    source=f"custom_{function_name}",
                )

                try:
                    # Execute custom function
                    result_str = await self._execute_custom_tool(
                        {
                            "name": function_name,
                            "arguments": json.dumps(tool_call["function"]["arguments"]) if isinstance(tool_call["function"].get("arguments"), (dict, list)) else tool_call["function"].get("arguments", "{}"),
                            "call_id": tool_call["id"],
                        }
                    )
                    if not result_str or result_str.startswith("Error:"):
                        logger.warning(f"Custom function {function_name} failed: {result_str or 'unknown error'}")
                        result_str = result_str or "Tool execution failed"
                except Exception as e:
                    logger.error(f"Unexpected error in custom function execution: {e}")
                    result_str = f"Error executing custom tool: {str(e)}"

                # Build tool result message
                tool_result_msg = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call["id"],
                            "content": result_str,
                        },
                    ],
                }

                # Append to updated_messages
                updated_messages.append(tool_result_msg)

                yield StreamChunk(
                    type="custom_tool_status",
                    status="function_call",
                    content=f"Arguments for Calling {function_name}: {json.dumps(tool_call['function'].get('arguments', {}))}",
                    source=f"custom_{function_name}",
                )

                yield StreamChunk(
                    type="custom_tool_status",
                    status="function_call_output",
                    content=f"Results for Calling {function_name}: {result_str}",
                    source=f"custom_{function_name}",
                )

                logger.info(f"Executed custom function {function_name}")
                yield StreamChunk(
                    type="custom_tool_status",
                    status="custom_tool_response",
                    content=f"✅ [Custom Tool] {function_name} completed",
                    source=f"custom_{function_name}",
                )

            # Then execute MCP tool calls and append results
            for tool_call in mcp_tool_calls:
                function_name = tool_call["function"]["name"]

                # Yield MCP tool call status
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_called",
                    content=f"🔧 [MCP Tool] Calling {function_name}...",
                    source=f"mcp_{function_name}",
                )

                try:
                    # Execute MCP function
                    args_json = json.dumps(tool_call["function"]["arguments"]) if isinstance(tool_call["function"].get("arguments"), (dict, list)) else tool_call["function"].get("arguments", "{}")
                    result_list = await self._execute_mcp_function_with_retry(function_name, args_json)
                    if not result_list or (isinstance(result_list[0], str) and result_list[0].startswith("Error:")):
                        logger.warning(f"MCP function {function_name} failed after retries: {result_list[0] if result_list else 'unknown error'}")
                        continue
                    result_str = result_list[0]
                    result_obj = result_list[1] if len(result_list) > 1 else None
                except Exception as e:
                    logger.error(f"Unexpected error in MCP function execution: {e}")
                    continue

                # Build tool result message: { "role":"user", "content":[{ "type":"tool_result", "tool_use_id": tool_call["id"], "content": result_str }] }
                tool_result_msg = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call["id"],
                            "content": result_str,
                        },
                    ],
                }

                # Append to updated_messages
                updated_messages.append(tool_result_msg)

                yield StreamChunk(
                    type="mcp_status",
                    status="function_call",
                    content=f"Arguments for Calling {function_name}: {json.dumps(tool_call['function'].get('arguments', {}))}",
                    source=f"mcp_{function_name}",
                )

                # If result_obj might be structured, try to display summary
                result_display = None
                try:
                    if hasattr(result_obj, "content") and result_obj.content:
                        part = result_obj.content[0]
                        if hasattr(part, "text"):
                            result_display = str(part.text)
                except Exception:
                    result_display = None
                if result_display:
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {result_display}",
                        source=f"mcp_{function_name}",
                    )
                else:
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {result_str}",
                        source=f"mcp_{function_name}",
                    )

                logger.info(f"Executed MCP function {function_name} (stdio/streamable-http)")
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_response",
                    content=f"✅ [MCP Tool] {function_name} completed",
                    source=f"mcp_{function_name}",
                )

            # Trim updated_messages using base class method
            updated_messages = self._trim_message_history(updated_messages)

            # After processing all tool calls, recurse
            async for chunk in self._stream_with_custom_and_mcp_tools(updated_messages, tools, client, **kwargs):
                yield chunk
            return
        else:
            # No MCP function calls; finalize this turn
            # Ensure termination with a done chunk when no further tool calls
            complete_message = {
                "role": "assistant",
                "content": content.strip(),
            }
            log_stream_chunk("backend.claude", "complete_message", complete_message, agent_id)
            yield StreamChunk(type="complete_message", complete_message=complete_message)
            yield StreamChunk(
                type="mcp_status",
                status="mcp_session_complete",
                content="✅ [MCP] Session completed",
                source="mcp_session",
            )
            yield StreamChunk(type="done")
            return

    async def _process_stream(
        self,
        stream,
        all_params: Dict[str, Any],
        agent_id: Optional[str],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Process stream events and yield StreamChunks."""
        content_local = ""
        current_tool_uses_local: Dict[str, Dict[str, Any]] = {}

        async for chunk in stream:
            try:
                if chunk.type == "message_start":
                    continue
                elif chunk.type == "content_block_start":
                    if hasattr(chunk, "content_block"):
                        if chunk.content_block.type == "tool_use":
                            tool_id = chunk.content_block.id
                            tool_name = chunk.content_block.name
                            current_tool_uses_local[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(chunk, "index", None),
                            }
                        elif chunk.content_block.type == "server_tool_use":
                            tool_id = chunk.content_block.id
                            tool_name = chunk.content_block.name
                            current_tool_uses_local[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(chunk, "index", None),
                                "server_side": True,
                            }
                            if tool_name == "code_execution":
                                yield StreamChunk(
                                    type="content",
                                    content="\n💻 [Code Execution] Starting...\n",
                                )
                            elif tool_name == "web_search":
                                yield StreamChunk(
                                    type="content",
                                    content="\n🔍 [Web Search] Starting search...\n",
                                )
                        elif chunk.content_block.type == "code_execution_tool_result":
                            result_block = chunk.content_block
                            result_parts = []
                            if hasattr(result_block, "stdout") and result_block.stdout:
                                result_parts.append(f"Output: {result_block.stdout.strip()}")
                            if hasattr(result_block, "stderr") and result_block.stderr:
                                result_parts.append(f"Error: {result_block.stderr.strip()}")
                            if hasattr(result_block, "return_code") and result_block.return_code != 0:
                                result_parts.append(f"Exit code: {result_block.return_code}")
                            if result_parts:
                                result_text = f"\n💻 [Code Execution Result]\n{chr(10).join(result_parts)}\n"
                                yield StreamChunk(
                                    type="content",
                                    content=result_text,
                                )
                elif chunk.type == "content_block_delta":
                    if hasattr(chunk, "delta"):
                        if chunk.delta.type == "text_delta":
                            text_chunk = chunk.delta.text
                            content_local += text_chunk
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": text_chunk},
                                backend_name="claude",
                            )
                            log_stream_chunk(
                                "backend.claude",
                                "content",
                                text_chunk,
                                agent_id,
                            )
                            yield StreamChunk(type="content", content=text_chunk)
                        elif chunk.delta.type == "input_json_delta":
                            if hasattr(chunk, "index"):
                                for (
                                    tool_id,
                                    tool_data,
                                ) in current_tool_uses_local.items():
                                    if tool_data.get("index") == chunk.index:
                                        partial_json = getattr(
                                            chunk.delta,
                                            "partial_json",
                                            "",
                                        )
                                        tool_data["input"] += partial_json
                                        break
                elif chunk.type == "content_block_stop":
                    if hasattr(chunk, "index"):
                        for (
                            tool_id,
                            tool_data,
                        ) in current_tool_uses_local.items():
                            if tool_data.get("index") == chunk.index and tool_data.get("server_side"):
                                tool_name = tool_data.get("name", "")
                                tool_input = tool_data.get("input", "")
                                try:
                                    parsed_input = json.loads(tool_input) if tool_input else {}
                                except json.JSONDecodeError:
                                    parsed_input = {"raw_input": tool_input}
                                if tool_name == "code_execution":
                                    code = parsed_input.get("code", "")
                                    if code:
                                        yield StreamChunk(
                                            type="content",
                                            content=f"💻 [Code] {code}\n",
                                        )
                                    yield StreamChunk(
                                        type="content",
                                        content="✅ [Code Execution] Completed\n",
                                    )
                                elif tool_name == "web_search":
                                    query = parsed_input.get("query", "")
                                    if query:
                                        yield StreamChunk(
                                            type="content",
                                            content=f"🔍 [Query] '{query}'\n",
                                        )
                                    yield StreamChunk(
                                        type="content",
                                        content="✅ [Web Search] Completed\n",
                                    )
                                tool_data["processed"] = True
                                break
                elif chunk.type == "message_delta":
                    pass
                elif chunk.type == "message_stop":
                    # Build final response and yield tool_calls for user-defined non-MCP tools
                    user_tool_calls = []
                    for tool_use in current_tool_uses_local.values():
                        tool_name = tool_use.get("name", "")
                        is_server_side = tool_use.get("server_side", False)
                        if not is_server_side and tool_name not in ["web_search", "code_execution"]:
                            tool_input = tool_use.get("input", "")
                            try:
                                parsed_input = json.loads(tool_input) if tool_input else {}
                            except json.JSONDecodeError:
                                parsed_input = {"raw_input": tool_input}
                            user_tool_calls.append(
                                {
                                    "id": tool_use["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": parsed_input,
                                    },
                                },
                            )

                    if user_tool_calls:
                        log_stream_chunk(
                            "backend.claude",
                            "tool_calls",
                            user_tool_calls,
                            agent_id,
                        )
                        yield StreamChunk(
                            type="tool_calls",
                            tool_calls=user_tool_calls,
                        )

                    complete_message = {
                        "role": "assistant",
                        "content": content_local.strip(),
                    }
                    if user_tool_calls:
                        complete_message["tool_calls"] = user_tool_calls
                    log_stream_chunk(
                        "backend.claude",
                        "complete_message",
                        complete_message,
                        agent_id,
                    )
                    yield StreamChunk(
                        type="complete_message",
                        complete_message=complete_message,
                    )

                    # Track usage for pricing
                    if all_params.get("enable_web_search", False):
                        self.search_count += 1
                    if all_params.get("enable_code_execution", False):
                        self.code_session_hours += 0.083

                    log_stream_chunk("backend.claude", "done", None, agent_id)
                    yield StreamChunk(type="done")
                    return
            except Exception as event_error:
                error_msg = f"Event processing error: {event_error}"
                log_stream_chunk("backend.claude", "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

    async def _handle_mcp_error_and_fallback(
        self,
        error: Exception,
        api_params: Dict[str, Any],
        provider_tools: List[Dict[str, Any]],
        stream_func: Callable[[Dict[str, Any]], AsyncGenerator[StreamChunk, None]],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle MCP errors with user-friendly messaging and fallback to non-MCP tools."""

        async with self._stats_lock:
            self._mcp_tool_failures += 1
            call_index_snapshot = self._mcp_tool_calls_count

        if MCPErrorHandler:
            log_type, user_message, _ = MCPErrorHandler.get_error_details(error)  # type: ignore[assignment]
        else:
            log_type, user_message = "mcp_error", "[MCP] Error occurred"

        logger.warning(f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}")

        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

        # Build non-MCP configuration and stream fallback
        fallback_params = dict(api_params)

        # Remove any MCP tools from the tools list
        if "tools" in fallback_params and self._mcp_functions:
            mcp_names = set(self._mcp_functions.keys())
            non_mcp_tools = []
            for tool in fallback_params["tools"]:
                name = tool.get("name")
                if name in mcp_names:
                    continue
                non_mcp_tools.append(tool)
            fallback_params["tools"] = non_mcp_tools

        # Add back provider tools if they were present
        if provider_tools:
            if "tools" not in fallback_params:
                fallback_params["tools"] = []
            fallback_params["tools"].extend(provider_tools)

        async for chunk in stream_func(fallback_params):
            yield chunk

    async def _execute_mcp_function_with_retry(
        self,
        function_name: str,
        arguments_json: str,
        max_retries: int = 3,
    ) -> List[str | Any]:
        """Execute MCP function with Claude-specific formatting."""
        # Use parent class method which returns tuple
        result_str, result_obj = await super()._execute_mcp_function_with_retry(
            function_name,
            arguments_json,
            max_retries,
        )

        # Convert to list format expected by Claude streaming
        if result_str.startswith("Error:"):
            return [result_str]
        return [result_str, result_obj]

    def create_tool_result_message(self, tool_call: Dict[str, Any], result_content: str) -> Dict[str, Any]:
        """Create tool result message in Claude's expected format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result_content,
                },
            ],
        }

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """Extract content from Claude tool result message."""
        content = tool_result_message.get("content", [])
        if isinstance(content, list) and content:
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    return item.get("content", "")
        return ""

    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_session_hours = 0.0
        super().reset_token_usage()

    def _create_client(self, **kwargs):
        return anthropic.AsyncAnthropic(api_key=self.api_key)

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Claude"

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Claude."""
        return ["web_search", "code_execution"]

    def get_filesystem_support(self) -> FilesystemSupport:
        """Claude supports filesystem through MCP servers."""
        return FilesystemSupport.MCP