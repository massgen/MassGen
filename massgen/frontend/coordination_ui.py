"""
MassGen Coordination UI

Main interface for coordinating agents with visual display.
"""

import asyncio
import json
import logging
import queue
import re
import threading
from typing import Any

from ..cancellation import CancellationRequested
from ..logger_config import get_event_emitter
from .displays.base_display import BaseDisplay
from .displays.content_normalizer import ContentNormalizer
from .displays.none_display import NoneDisplay
from .displays.rich_terminal_display import RichTerminalDisplay, is_rich_available
from .displays.silent_display import SilentDisplay
from .displays.simple_display import SimpleDisplay
from .displays.terminal_display import TerminalDisplay

try:
    from .displays.textual_terminal_display import (
        TextualTerminalDisplay,
        is_textual_available,
    )
except ImportError:
    TextualTerminalDisplay = None

    def is_textual_available():
        return False


try:
    from .displays.web_display import WebDisplay, is_web_display_available
except ImportError:
    WebDisplay = None

    def is_web_display_available():
        return False


logger = logging.getLogger(__name__)


class CoordinationUI:
    """Main coordination interface with display capabilities."""

    def __init__(
        self,
        display: BaseDisplay | None = None,
        logger: Any | None = None,
        display_type: str = "textual_terminal",
        enable_final_presentation: bool = False,
        preserve_display: bool = False,
        interactive_mode: bool = False,
        **kwargs,
    ):
        """Initialize coordination UI.

        Args:
            display: Custom display instance (overrides display_type)
            logger: Custom logger instance
            display_type: Type of display ("terminal", "simple", "rich_terminal", "textual_terminal", "web")
            enable_final_presentation: Whether to ask winning agent to present final answer
            preserve_display: If True, don't cleanup/recreate display between turns (for multi-turn TUI)
            interactive_mode: If True, external driver owns the TUI loop (don't call display.run_async())
            **kwargs: Additional configuration passed to display/logger
        """
        self.enable_final_presentation = enable_final_presentation
        self.display = display
        self.logger = logger
        self.display_type = display_type
        self.config = kwargs

        # Multi-turn display preservation mode
        self.preserve_display = preserve_display
        self.interactive_mode = interactive_mode

        # Will be set during coordination
        self.agent_ids = []
        self.orchestrator = None

        # Flush output configuration (matches rich_terminal_display)
        self._flush_char_delay = 0.03  # 30ms between characters

        # Initialize answer buffer state
        self._answer_buffer = ""
        self._answer_timeout_task = None
        self._final_answer_shown = False

        # Status bar tracking
        self._last_phase = "idle"

        # Per-agent content buffer for filtering workspace tool JSON
        # Streaming sends small chunks that individually don't match patterns,
        # so we buffer until we see a complete line or JSON block
        self._agent_content_buffers: dict[str, str] = {}

    def _process_reasoning_summary(self, chunk_type: str, summary_delta: str, source: str) -> str:
        """Process reasoning summary content using display's shared logic."""
        if self.display and hasattr(self.display, "process_reasoning_content"):
            return self.display.process_reasoning_content(chunk_type, summary_delta, source)
        else:
            # Fallback logic if no display available
            if chunk_type == "reasoning_summary":
                summary_active_key = f"_summary_active_{source}"
                if not getattr(self, summary_active_key, False):
                    setattr(self, summary_active_key, True)
                    return f"📋 [Reasoning Summary]\n{summary_delta}\n"
                return summary_delta
            elif chunk_type == "reasoning_summary_done":
                summary_active_key = f"_summary_active_{source}"
                if hasattr(self, summary_active_key):
                    setattr(self, summary_active_key, False)
            return summary_delta

    def _process_reasoning_content(self, chunk_type: str, reasoning_delta: str, source: str) -> str:
        """Process reasoning summary content using display's shared logic."""
        if self.display and hasattr(self.display, "process_reasoning_content"):
            return self.display.process_reasoning_content(chunk_type, reasoning_delta, source)
        else:
            # Fallback logic if no display available
            if chunk_type == "reasoning":
                reasoning_active_key = f"_reasoning_active_{source}"
                if not getattr(self, reasoning_active_key, False):
                    setattr(self, reasoning_active_key, True)
                    return f"🧠 [Reasoning Started]\n{reasoning_delta}\n"
                return reasoning_delta
            elif chunk_type == "reasoning_done":
                reasoning_active_key = f"_reasoning_active_{source}"
                if hasattr(self, reasoning_active_key):
                    setattr(self, reasoning_active_key, False)
                return reasoning_delta

    def _parse_chunk_data(self, chunk: Any, content: Any) -> dict[str, Any] | None:
        """Parse structured data from a chunk.

        Tries in order:
        1. chunk.data attribute (if exists)
        2. content if already a dict
        3. content parsed as JSON string

        Args:
            chunk: The chunk object that may have a 'data' attribute
            content: The content which may be a dict or JSON string

        Returns:
            Parsed dict or None if parsing fails
        """
        # Try chunk.data first
        data = getattr(chunk, "data", None)
        if isinstance(data, dict):
            return data

        # Content might already be a dict (orchestrator passes dict directly)
        if isinstance(content, dict):
            return content

        # Try parsing content as JSON string
        if isinstance(content, str) and content:
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    def _reset_summary_active_flags(self) -> None:
        """Reset all _summary_active_ flags for final presentation."""
        for attr_name in list(vars(self).keys()):
            if attr_name.startswith("_summary_active_"):
                delattr(self, attr_name)

    def _check_and_dispatch_rework_signal(self, orchestrator: Any) -> None:
        """Consume a pending rework signal from the orchestrator and dispatch it.

        The orchestrator sets ``_pending_review_rework`` when the user requests
        a rework/quick-fix from the review modal.  This helper is called from
        the three final-presentation code-paths so the signal is consumed
        exactly once and forwarded to the display layer.
        """
        import logging

        _logger = logging.getLogger(__name__)

        pending_rework = getattr(orchestrator, "_pending_review_rework", None)
        if not pending_rework:
            return

        orchestrator._pending_review_rework = None  # Consume the signal
        _logger.info("[CoordinationUI] Consumed rework signal: action=%s", pending_rework.get("action"))

        if self.display and hasattr(self.display, "_dispatch_review_rework"):
            self.display._dispatch_review_rework(pending_rework)
        else:
            _logger.warning(
                "[CoordinationUI] Rework signal dropped — display lacks _dispatch_review_rework",
            )

    def _handle_coordination_chunk(
        self,
        chunk_type: str,
        chunk: Any,
        content: str,
        orchestrator: Any,
    ) -> bool:
        """Handle coordination-related chunk types consistently.

        Args:
            chunk_type: The type of chunk being processed
            chunk: The chunk object
            content: The content string from the chunk
            orchestrator: The orchestrator instance for restart info

        Returns:
            True if the chunk was handled (caller should continue to next chunk),
            False if the chunk was not handled by this method
        """
        if chunk_type == "restart_banner":
            # Extract restart info from orchestrator state
            reason = getattr(orchestrator, "restart_reason", "Answer needs improvement")
            instructions = getattr(
                orchestrator,
                "restart_instructions",
                "Please address the issues identified",
            )
            # Next attempt number (current is 0-indexed, so +2 for next attempt)
            attempt = getattr(orchestrator, "current_attempt", 0) + 2
            max_attempts = getattr(orchestrator, "max_attempts", 3)

            if self.display and hasattr(self.display, "show_restart_banner"):
                self.display.show_restart_banner(reason, instructions, attempt, max_attempts)
            # Emit structured event

            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_restart_banner(reason, instructions, attempt, max_attempts)
            return True

        elif chunk_type == "restart_required":
            # Signal that orchestration will restart - UI will be reinitialized
            return True

        elif chunk_type == "agent_restart":
            # Agent is starting a new round due to new context from other agents
            data = self._parse_chunk_data(chunk, content)

            # When the unified event pipeline is active, emit the structured event
            # so the pipeline can render the round banner AFTER processing preceding
            # events (answer_submitted, vote) for correct chronological ordering.
            # When NOT active, use the direct display path instead.
            pipeline_active = bool(getattr(self.display, "_event_listener_registered", False))

            if not pipeline_active:
                # Fallback direct path when event pipeline is not active
                if self.display and hasattr(self.display, "show_agent_restart"):
                    if data:
                        agent_id = data.get("agent_id")
                        round_num = data.get("round", 1)
                        if agent_id:
                            self.display.show_agent_restart(agent_id, round_num)

            # Emit structured event (always, for logging and event pipeline)
            _emitter = get_event_emitter()
            if _emitter and data:
                _emitter.emit_agent_restart(
                    data.get("round", 1),
                    agent_id=data.get("agent_id"),
                    restart_reason=data.get("restart_reason"),
                )
            return True

        elif chunk_type == "final_presentation_start":
            data = self._parse_chunk_data(chunk, content)
            # Set flag IMMEDIATELY to prevent race with content chunks
            # (content chunks may arrive before the event is processed)
            if self.display and hasattr(self.display, "_in_final_presentation"):
                self.display._in_final_presentation = True
            # When the unified event pipeline is active, emit the structured event
            # so the pipeline can render the final presentation banner.
            # When NOT active, use the direct display path instead.
            pipeline_active = bool(getattr(self.display, "_event_listener_registered", False))
            if pipeline_active:
                # Emit structured event for the event pipeline to handle
                _emitter = get_event_emitter()
                if _emitter and data:
                    _emitter.emit_presentation_start(
                        agent_id=data.get("agent_id"),
                        vote_counts=data.get("vote_counts"),
                        answer_labels=data.get("answer_labels"),
                    )
            elif self.display and hasattr(self.display, "show_final_presentation_start"):
                if data:
                    agent_id = data.get("agent_id")
                    vote_counts = data.get("vote_counts")
                    answer_labels = data.get("answer_labels")
                    if agent_id:
                        self.display.show_final_presentation_start(
                            agent_id,
                            vote_counts=vote_counts,
                            answer_labels=answer_labels,
                        )
            # Reset reasoning prefix state
            self._reset_summary_active_flags()
            return True

        return False

    def __post_init__(self):
        """Post-initialization setup."""
        self._flush_word_delay = 0.08  # 80ms after punctuation

        # Initialize answer buffer state
        self._answer_buffer = ""
        self._answer_timeout_task = None
        self._final_answer_shown = False

    async def _run_orchestration(self, orchestrator, question: str) -> str:
        """Run the actual orchestration logic (can be in any thread)."""
        # Debug log entry
        try:
            from massgen.frontend.displays.textual_terminal_display import tui_log

            tui_log(f"_run_orchestration STARTING for question: {question[:50]}...")
        except Exception:
            pass

        # Initialize variables
        selected_agent = None
        vote_results = {}
        user_quit = False
        full_response = ""
        final_answer = ""

        try:
            # Process coordination stream
            async for chunk in orchestrator.chat_simple(question):
                # Check if user requested quit (pressed 'q' in Rich display)
                if self.display and hasattr(self.display, "_user_quit_requested") and self.display._user_quit_requested:
                    # User pressed 'q' - cancel current turn, not entire session
                    user_quit = True
                    raise CancellationRequested(partial_saved=False)

                # Check if Ctrl+C was pressed (cancellation manager flag)
                if hasattr(orchestrator, "cancellation_manager") and orchestrator.cancellation_manager and orchestrator.cancellation_manager.is_cancelled:
                    user_quit = True
                    # Update display to show cancellation status before stopping
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status("⏸️ Cancelling turn...")
                    raise CancellationRequested(partial_saved=orchestrator.cancellation_manager._partial_saved)

                # Unpack legacy tuple format from orchestrator
                # Some code paths yield ("type", StreamChunk/content, ...) tuples
                if isinstance(chunk, tuple):
                    if len(chunk) >= 2 and hasattr(chunk[1], "type"):
                        # ("reasoning", StreamChunk(...)) — use the StreamChunk
                        chunk = chunk[1]
                    elif len(chunk) >= 2:
                        # ("content", "text") or ("type", content, extra...)
                        from massgen.backend.base import StreamChunk as _SC

                        chunk = _SC(type=chunk[0], content=str(chunk[1]) if chunk[1] else "")

                content = getattr(chunk, "content", "") or ""
                source = getattr(chunk, "source", None)
                chunk_type_raw = getattr(chunk, "type", "")
                chunk_type = chunk_type_raw.value if hasattr(chunk_type_raw, "value") else str(chunk_type_raw) if chunk_type_raw else ""

                # Check for phase changes and notify status bar
                if hasattr(orchestrator, "workflow_phase"):
                    current_phase = orchestrator.workflow_phase
                    if current_phase != self._last_phase:
                        old_phase = self._last_phase
                        self._last_phase = current_phase
                        # Debug log for phase changes
                        try:
                            from massgen.frontend.displays.textual_terminal_display import (
                                tui_log,
                            )

                            tui_log(f"CoordinationUI: phase changed '{old_phase}' -> '{current_phase}'")
                        except Exception:
                            pass
                        if hasattr(self.display, "notify_phase"):
                            tui_log(f"  Calling display.notify_phase('{current_phase}')")
                            self.display.notify_phase(current_phase)
                        # Emit structured event for phase changes

                        _emitter = get_event_emitter()
                        if _emitter:
                            _emitter.emit_phase_change(current_phase)

                # Handle agent status updates
                if chunk_type == "agent_status":
                    status = getattr(chunk, "status", None)
                    if self.display and source and status:
                        self.display.update_agent_status(source, status)
                    # Emit structured event
                    if source and status:
                        _emitter = get_event_emitter()
                        if _emitter:
                            _emitter.emit_status(f"Agent status: {status}", agent_id=source)
                    continue

                # Phase 13.1: Handle token usage updates for status ribbon
                elif chunk_type == "token_usage_update":
                    usage = getattr(chunk, "usage", {})
                    if self.display and source and hasattr(self.display, "update_token_usage"):
                        self.display.update_token_usage(source, usage)
                    continue

                # Handle system status updates (e.g., "Initializing coordination...", "Preparing agents...")
                elif chunk_type == "system_status":
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status(content)

                    _emitter = get_event_emitter()
                    if _emitter and content:
                        _emitter.emit_system_status(content)
                    continue

                # Filter out debug chunks from display
                elif chunk_type == "debug":
                    # Log debug info but don't display it
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Handle cancelled chunk from orchestrator (e.g., during final presentation)
                elif chunk_type == "cancelled":
                    user_quit = True
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status("⏸️ Cancelling turn...")
                    partial_saved = orchestrator.cancellation_manager._partial_saved if hasattr(orchestrator, "cancellation_manager") and orchestrator.cancellation_manager else False
                    raise CancellationRequested(partial_saved=partial_saved)

                # Filter out tool status chunks - display via agent panel instead of console
                elif chunk_type in ("mcp_status", "custom_tool_status"):
                    # Let the display handle tool status via agent panel
                    # source may be agent_id or tool name (e.g., "mcp_mcp__filesystem__write_file")
                    target_agent = source if source in self.agent_ids else None
                    if not target_agent and self.agent_ids:
                        # Fallback: route to first agent if source is a tool name
                        target_agent = self.agent_ids[0]
                    if self.display and target_agent:
                        self.display.update_agent_content(
                            target_agent,
                            content,
                            "tool",
                            tool_call_id=chunk.tool_call_id,
                        )
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Display compression status - show in agent panel
                elif chunk_type == "compression_status":
                    target_agent = source if source in self.agent_ids else None
                    if not target_agent and self.agent_ids:
                        target_agent = self.agent_ids[0]
                    if self.display and target_agent:
                        self.display.update_agent_content(target_agent, content, "tool")
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Handle hook execution events - route to display
                elif chunk_type == "hook_execution":
                    hook_info = getattr(chunk, "hook_info", None)
                    tool_call_id = getattr(chunk, "tool_call_id", None)
                    from massgen.logger_config import logger as hook_logger

                    hook_logger.info(
                        f"[CoordinationUI] hook_execution chunk received: source={source}, "
                        f"tool_call_id={tool_call_id}, has_hook_info={hook_info is not None}, "
                        f"has_display={self.display is not None}, "
                        f"display_has_method={hasattr(self.display, 'update_hook_execution') if self.display else False}",
                    )
                    if self.display and source and hook_info:
                        if hasattr(self.display, "update_hook_execution"):
                            hook_logger.info("[CoordinationUI] Calling display.update_hook_execution")
                            self.display.update_hook_execution(source, tool_call_id, hook_info)
                        else:
                            hook_logger.warning("[CoordinationUI] display missing update_hook_execution method")
                    # Only emit hook events that have meaningful content (injection or non-allow decision)
                    if hook_info:
                        _decision = hook_info.get("decision", "allow") if isinstance(hook_info, dict) else "allow"
                        _has_injection = bool(hook_info.get("injection_content")) if isinstance(hook_info, dict) else False
                        if _decision != "allow" or _has_injection:
                            _emitter = get_event_emitter()
                            if _emitter:
                                _emitter.emit_hook_execution(tool_call_id, hook_info, agent_id=source)
                    if self.logger:
                        self.logger.log_chunk(source, str(hook_info), chunk_type)
                    continue

                # Handle reasoning streams
                elif chunk_type in [
                    "reasoning",
                    "reasoning_done",
                    "reasoning_summary",
                    "reasoning_summary_done",
                ]:
                    if source:
                        reasoning_content = ""
                        if chunk_type == "reasoning":
                            # Stream reasoning delta as thinking content
                            reasoning_delta = getattr(chunk, "reasoning_delta", "")
                            if reasoning_delta:
                                reasoning_content = self._process_reasoning_content(chunk_type, reasoning_delta, source)
                        elif chunk_type == "reasoning_done":
                            # Complete reasoning text
                            reasoning_text = getattr(chunk, "reasoning_text", "")
                            if reasoning_text:
                                reasoning_content = f"\n🧠 [Reasoning Complete]\n{reasoning_text}\n"
                            else:
                                reasoning_content = "\n🧠 [Reasoning Complete]\n"

                            # Reset flag using helper method
                            self._process_reasoning_content(chunk_type, reasoning_content, source)

                            # Mark summary as complete - next summary can get a prefix
                            reasoning_active_key = "_reasoning_active"
                            if hasattr(self, reasoning_active_key):
                                delattr(self, reasoning_active_key)

                        elif chunk_type == "reasoning_summary":
                            # Stream reasoning summary delta
                            summary_delta = getattr(chunk, "reasoning_summary_delta", "")
                            if summary_delta:
                                reasoning_content = self._process_reasoning_summary(chunk_type, summary_delta, source)
                        elif chunk_type == "reasoning_summary_done":
                            # Complete reasoning summary
                            summary_text = getattr(chunk, "reasoning_summary_text", "")
                            if summary_text:
                                reasoning_content = f"\n📋 [Reasoning Summary Complete]\n{summary_text}\n"

                            # Reset flag using helper method
                            self._process_reasoning_summary(chunk_type, "", source)

                            # Mark summary as complete - next summary can get a prefix
                            summary_active_key = f"_summary_active_{source}"
                            if hasattr(self, summary_active_key):
                                delattr(self, summary_active_key)

                        if reasoning_content:
                            # Display reasoning as thinking content (old path - writes agent files)
                            if self.display:
                                self.display.update_agent_content(source, reasoning_content, "thinking")
                            if self.logger:
                                self.logger.log_agent_content(source, reasoning_content, "reasoning")
                    continue

                # Handle coordination chunk types (restart_banner, restart_required, agent_restart, final_presentation_start)
                if self._handle_coordination_chunk(chunk_type, chunk, content, orchestrator):
                    continue

                # Reset reasoning prefix state when final presentation starts (legacy fallback)
                if chunk_type == "status" and "presenting final answer" in content:
                    self._reset_summary_active_flags()

                # Handle post-evaluation content streaming
                # Event emission is handled by the orchestrator; coordination_ui
                # only routes content to the display layer.
                if source and content and chunk_type == "content":
                    # Check if we're in post-evaluation
                    if hasattr(self, "_in_post_evaluation") and self._in_post_evaluation:
                        if self.display and hasattr(self.display, "show_post_evaluation_content"):
                            self.display.show_post_evaluation_content(content, source)
                        # Content has been routed to post-eval panel, skip regular processing
                        continue

                # Track selected agent for post-evaluation
                if content and "🏆 Selected Agent:" in content:
                    import re

                    match = re.search(r"🏆 Selected Agent: (\S+)", content)
                    if match:
                        self._post_eval_winner = match.group(1)

                # Detect post-evaluation start
                if chunk_type == "status" and "Post-evaluation" in content:
                    self._in_post_evaluation = True
                    if self.display and hasattr(self.display, "_routing_to_post_eval_card"):
                        self.display._routing_to_post_eval_card = True

                # Detect post-evaluation completion and show footer
                if chunk_type == "status" and hasattr(self, "_in_post_evaluation") and self._in_post_evaluation:
                    if "Evaluation complete" in content or "Restart requested" in content:
                        self._in_post_evaluation = False
                        if self.display and hasattr(self.display, "_routing_to_post_eval_card"):
                            self.display._routing_to_post_eval_card = False
                        winner = getattr(self, "_post_eval_winner", None) or source
                        if self.display and hasattr(self.display, "end_post_evaluation_content"):
                            self.display.end_post_evaluation_content(winner)

                if content:
                    full_response += content

                    # Log chunk
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)

                    # Process content by source
                    # Bug 2 fix: Display-level flag prevents timeline routing, so no check needed here
                    await self._process_content(source, content, chunk_type)

            # Flush agent content buffers BEFORE processing final answer
            # This ensures any streamed content reaches the display before we complete
            try:
                if hasattr(self, "_agent_content_buffers") and self._agent_content_buffers:
                    await self._flush_agent_content_buffers()
            except asyncio.CancelledError:
                pass

            # Get final presentation content from orchestrator state
            status = orchestrator.get_status()
            vote_results = status.get("vote_results", {})
            selected_agent = status.get("selected_agent", "")

            # Get the final presentation content from orchestrator state
            orchestrator_final_answer = None
            if hasattr(orchestrator, "_final_presentation_content") and orchestrator._final_presentation_content:
                orchestrator_final_answer = orchestrator._final_presentation_content.strip()
            elif selected_agent and hasattr(orchestrator, "agent_states") and selected_agent in orchestrator.agent_states:
                # Fall back to stored answer if no final presentation content
                stored_answer = orchestrator.agent_states[selected_agent].answer
                if stored_answer:
                    orchestrator_final_answer = stored_answer.strip()

            # Check for review rework signal from orchestrator
            self._check_and_dispatch_rework_signal(orchestrator)

            # Use orchestrator's clean answer or fall back to full response
            final_result = orchestrator_final_answer if orchestrator_final_answer else full_response

            # Ensure display shows final answer even if streaming chunks were filtered
            # This applies to all display types that have show_final_answer method
            # Only show if we have a valid selected agent (don't create "Unknown" files)
            if hasattr(self.display, "show_final_answer") and not self._final_answer_shown and selected_agent:
                display_answer = (final_result or "").strip()
                if display_answer:
                    self._final_answer_shown = True
                    self.display.show_final_answer(
                        display_answer,
                        vote_results=vote_results,
                        selected_agent=selected_agent,
                    )

            # Finalize session if logger exists
            if self.logger:
                session_info = self.logger.finalize_session(
                    final_result if "final_result" in locals() else (final_answer if "final_answer" in locals() else ""),
                    success=True,
                )
                # Note: Don't print here - let the calling method handle display

            return final_result

        except CancellationRequested:
            # User pressed 'q' to cancel turn - propagate up to CLI
            # Don't mark as failed - this is a soft cancellation
            if self.logger:
                self.logger.finalize_session("Turn cancelled by user", success=True)
            raise

        except SystemExit:
            # Hard exit requested - cleanup and exit gracefully
            if self.logger:
                self.logger.finalize_session("User quit", success=True)
            # Cleanup agent backends
            if hasattr(orchestrator, "agents"):
                for agent_id, agent in orchestrator.agents.items():
                    if hasattr(agent, "cleanup"):
                        try:
                            agent.cleanup()
                        except Exception:
                            pass
            raise

        except Exception:
            # Log error and re-raise
            if self.logger:
                self.logger.finalize_session("", success=False)
            raise

        finally:
            # Wait for any pending timeout task to complete before cleanup
            if hasattr(self, "_answer_timeout_task") and self._answer_timeout_task:
                try:
                    # Give the task a chance to complete
                    await asyncio.wait_for(self._answer_timeout_task, timeout=1.0)
                except (TimeoutError, asyncio.CancelledError):
                    # If it takes too long or was cancelled, force flush
                    try:
                        if hasattr(self, "_answer_buffer") and self._answer_buffer and not self._final_answer_shown:
                            await self._flush_final_answer()
                    except asyncio.CancelledError:
                        pass
                    try:
                        self._answer_timeout_task.cancel()
                    except Exception:
                        pass

            # Final check to flush any remaining buffered answer
            try:
                if hasattr(self, "_answer_buffer") and self._answer_buffer and not self._final_answer_shown:
                    await self._flush_final_answer()
            except asyncio.CancelledError:
                pass

            # Flush any remaining agent content buffers
            try:
                if hasattr(self, "_agent_content_buffers") and self._agent_content_buffers:
                    await self._flush_agent_content_buffers()
            except asyncio.CancelledError:
                pass

            # Small delay to ensure display updates are processed
            try:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass

            # Determine if coordination completed successfully
            is_finished = hasattr(orchestrator, "workflow_phase") and orchestrator.workflow_phase == "presenting"

            # Cleanup display resources (stop live, restore terminal) unless in preserve_display mode
            # In preserve_display mode (multi-turn TUI), the external driver owns the display lifecycle
            if self.display and not self.preserve_display:
                try:
                    self.display.cleanup()
                except Exception:
                    # Fallback: at minimum stop the live display
                    if hasattr(self.display, "live") and self.display.live:
                        try:
                            self.display.live.stop()
                        except Exception:
                            pass

            # Always save coordination logs - even for incomplete runs
            # This ensures we capture partial progress for debugging/analysis
            try:
                if hasattr(orchestrator, "save_coordination_logs"):
                    # Check if logs were already saved (happens in finalize_presentation for complete runs)
                    if not is_finished:
                        orchestrator.save_coordination_logs()
            except Exception as e:
                import logging

                logging.getLogger("massgen").warning(f"Failed to save coordination logs: {e}")

    def reset(self):
        """Reset UI state for next coordination session."""
        # Clean up display if exists
        if self.display:
            try:
                self.display.cleanup()
            except Exception:
                pass  # Ignore cleanup errors
            self.display = None

        # Reset all state variables
        self.agent_ids = []
        self.orchestrator = None

        # Reset answer buffer state if they exist
        if hasattr(self, "_answer_buffer"):
            self._answer_buffer = ""
        if hasattr(self, "_answer_timeout_task") and self._answer_timeout_task:
            self._answer_timeout_task.cancel()
            self._answer_timeout_task = None
        if hasattr(self, "_final_answer_shown"):
            self._final_answer_shown = False

        # Reset content buffers
        if hasattr(self, "_agent_content_buffers"):
            self._agent_content_buffers = {}

    def prepare_for_restart(self, orchestrator, attempt: int, max_attempts: int) -> None:
        """Prepare the UI for a restart attempt without recreating display or UI.

        Resets internal state and tells the display to show a restart separator.

        Args:
            orchestrator: The orchestrator (used to extract restart context).
            attempt: The new attempt number (1-indexed).
            max_attempts: Total allowed attempts.
        """
        reason = getattr(orchestrator, "restart_reason", "") or ""
        instructions = getattr(orchestrator, "restart_instructions", "") or ""

        # Reset answer/presentation state
        self._answer_buffer = ""
        if self._answer_timeout_task:
            self._answer_timeout_task.cancel()
            self._answer_timeout_task = None
        self._final_answer_shown = False
        self._agent_content_buffers = {}
        self._last_phase = "idle"

        # Flag so coordinate() skips display cleanup on re-entry
        self._is_restart = True

        # Delegate to display
        if self.display and hasattr(self.display, "begin_restart"):
            self.display.begin_restart(attempt, max_attempts, reason, instructions)

    def _install_interactive_approval_provider(self, orchestrator) -> None:
        """Route per-tool `ask` approvals to the TUI modal when a real interactive
        display exists. No-op in automation/headless (the coordinator keeps its
        PolicyApprovalProvider) and for agents without a permission coordinator."""
        display = self.display
        if display is None or self.config.get("automation_mode", False):
            return
        if not hasattr(display, "show_tool_approval_modal"):
            return
        try:
            from massgen.permissions.approval_provider import (
                CallbackApprovalProvider,
                PolicyApprovalProvider,
            )
            from massgen.permissions.models import ApprovalDecision
        except Exception:
            return

        async def _approval_callback(authz):
            try:
                return await display.show_tool_approval_modal(authz)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[TUI] approval modal failed: {e}")
                return ApprovalDecision(allowed=False, feedback=f"Approval unavailable ({e}); denied.", operator="policy")

        for agent_id, agent in (getattr(orchestrator, "agents", {}) or {}).items():
            backend = getattr(agent, "backend", None)
            coordinator = getattr(backend, "_permission_coordinator", None) if backend is not None else None
            if coordinator is None or not hasattr(backend, "set_approval_provider"):
                continue
            # Only take over the automation-policy provider — leave a file/remote
            # provider (approval_mode: file) in place even under a TUI.
            if not isinstance(coordinator.provider, PolicyApprovalProvider):
                continue
            backend.set_approval_provider(CallbackApprovalProvider(_approval_callback, fail_closed=True))
            logger.info(f"[TUI] Installed interactive approval provider for {agent_id}")

    async def coordinate(self, orchestrator, question: str, agent_ids: list[str] | None = None) -> str:
        """Coordinate agents with visual display.

        Args:
            orchestrator: MassGen orchestrator instance
            question: Question for coordination
            agent_ids: Optional list of agent IDs (auto-detected if not provided)

        Returns:
            Final coordinated response
        """
        from massgen.logger_config import logger as coord_logger

        coord_logger.info(f"[CoordinationUI] coordinate() method CALLED - question: {question[:50]}...")

        # Initialize variables that may be referenced in finally block
        selected_agent = ""
        vote_results = {}
        final_result = ""
        final_answer = ""

        # Check if this is a restart re-entry (display already prepared)
        is_restart = getattr(self, "_is_restart", False)
        if is_restart:
            self._is_restart = False

        # Reset display to ensure clean state for each coordination
        # But preserve web displays - they have their own lifecycle managed by the web server
        # Also preserve display in preserve_display mode (for multi-turn TUI)
        # Also skip cleanup on restart re-entry (display was already prepared)
        if self.display is not None and self.display_type != "web" and not self.preserve_display and not is_restart:
            self.display.cleanup()
            self.display = None

        self.orchestrator = orchestrator
        # Set bidirectional reference so orchestrator can access UI (for broadcast prompts)
        orchestrator.coordination_ui = self
        # Ensure workspace symlinks exist for the current turn/attempt log directory
        if hasattr(orchestrator, "ensure_workspace_symlinks"):
            try:
                orchestrator.ensure_workspace_symlinks()
            except Exception as e:
                coord_logger.warning(f"[CoordinationUI] Failed to create workspace symlinks: {e}")

        # Auto-detect agent IDs if not provided
        # Sort for consistent anonymous mapping with coordination_tracker
        if agent_ids is None:
            self.agent_ids = sorted(orchestrator.agents.keys())
        else:
            self.agent_ids = sorted(agent_ids)

        # Initialize display if not provided
        if self.display is None:
            if self.display_type == "terminal":
                self.display = TerminalDisplay(self.agent_ids, **self.config)
            elif self.display_type == "simple":
                self.display = SimpleDisplay(self.agent_ids, **self.config)
            elif self.display_type == "silent":
                self.display = SilentDisplay(self.agent_ids, **self.config)
            elif self.display_type == "none":
                self.display = NoneDisplay(self.agent_ids, **self.config)
            elif self.display_type == "rich_terminal":
                if not is_rich_available():
                    print("⚠️  Rich library not available. Falling back to terminal display.")
                    print("   Install with: pip install rich")
                    self.display = TerminalDisplay(self.agent_ids, **self.config)
                else:
                    self.display = RichTerminalDisplay(self.agent_ids, **self.config)
            elif self.display_type == "textual_terminal":
                if not is_textual_available():
                    print("⚠️  Textual library not available. Falling back to terminal display.")
                    print("   Install with: pip install textual")
                    self.display = TerminalDisplay(self.agent_ids, **self.config)
                else:
                    # Build agent_models dict for welcome screen
                    agent_models = {}
                    for agent_id, agent in orchestrator.agents.items():
                        if hasattr(agent, "backend") and hasattr(agent.backend, "model"):
                            agent_models[agent_id] = agent.backend.model
                        elif hasattr(agent, "config") and hasattr(agent.config, "backend_params"):
                            agent_models[agent_id] = agent.config.backend_params.get("model", "")
                    config_with_models = {**self.config, "agent_models": agent_models}
                    self.display = TextualTerminalDisplay(self.agent_ids, **config_with_models)
            elif self.display_type == "web":
                # WebDisplay must be passed in from the web server with broadcast configured
                if self.display is None:
                    raise ValueError(
                        "WebDisplay must be passed to CoordinationUI when using " "display_type='web'. Create it via the web server.",
                    )
                # Display already set - just use it
            else:
                raise ValueError(f"Unknown display type: {self.display_type}")

        # Pass orchestrator reference to display for backend info
        self.display.orchestrator = orchestrator

        # Set up subagent spawn callbacks AFTER display is initialized
        # so the callback can access the display for TUI notifications
        if hasattr(orchestrator, "setup_subagent_spawn_callbacks"):
            orchestrator.setup_subagent_spawn_callbacks()

        # Permissions: when a real interactive TUI exists, route per-tool `ask`
        # decisions to the approval MODAL (swapping out the automation-policy provider
        # each agent's coordinator was created with). Automation/headless keeps Policy.
        self._install_interactive_approval_provider(orchestrator)

        # Start lightweight event-driven agent output writer
        from massgen.frontend.agent_output_writer import create_agent_output_writer

        self._agent_output_writer = create_agent_output_writer(self.agent_ids)

        # Initialize answer buffering for preventing duplicate show_final_answer calls
        self._answer_buffer = ""
        self._answer_timeout_task = None
        self._final_answer_shown = False

        # Initialize logger and display
        log_filename = None
        if self.logger:
            log_filename = self.logger.initialize_session(question, self.agent_ids)
            monitoring = self.logger.get_monitoring_commands()
            print(f"📁 Real-time log: {log_filename}")
            print(f"💡 Monitor with: {monitoring['tail']}")
            print()

        self.display.initialize(question, log_filename)

        # Emit status that display is ready (for web UI)
        if hasattr(self.display, "_emit"):
            self.display._emit("preparation_status", {"status": "Display initialized...", "detail": "Starting orchestrator"})

        # Reset quit flag for new turn (allows 'q' to cancel this turn)
        if hasattr(self.display, "reset_quit_request"):
            self.display.reset_quit_request()

        # Initialize variables to avoid reference before assignment error in finally block
        selected_agent = None
        vote_results = {}
        user_quit = False  # Track if user quit

        # For Textual: Run in main thread, orchestration in background thread
        # Unless interactive_mode is True - then external driver owns the TUI loop
        if self.display_type == "textual_terminal" and is_textual_available() and not self.interactive_mode:
            # Use queue for exception propagation
            result_queue = queue.Queue()

            async def orchestration_wrapper():
                """Wrapper to capture exceptions from orchestration."""
                try:
                    answer = await self._run_orchestration(orchestrator, question)
                    result_queue.put(("success", answer))
                except SystemExit as quit_exc:
                    result_queue.put(("quit", quit_exc))
                except BaseException as exc:
                    result_queue.put(("error", exc))

            def run_async_orchestration():
                """Bridge between threading and asyncio."""
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(orchestration_wrapper())
                finally:
                    loop.close()

            # Start orchestration in background thread
            orchestrator_thread = threading.Thread(
                target=run_async_orchestration,
                daemon=False,
            )
            orchestrator_thread.start()

            # Run Textual in main thread
            try:
                await self.display.run_async()
            finally:
                # Clean up orchestration thread
                orchestrator_thread.join(timeout=5)
                if orchestrator_thread.is_alive():
                    import logging

                    logging.warning("Orchestration thread did not complete within timeout")

            # Get result from queue
            try:
                # Block briefly to give the orchestration thread time to publish its result
                status, result = result_queue.get(timeout=5)
                if status == "error":
                    raise result  # Re-raise exception from orchestration thread
                if status == "quit":
                    raise result  # Re-raise exception from orchestration thread
                return result
            except queue.Empty:
                # Thread didn't produce result
                raise RuntimeError(
                    "Orchestration thread did not produce a result. " "Check logs for errors.",
                )

        # For other displays: Run orchestration
        try:
            # Process coordination stream
            full_response = ""
            final_answer = ""

            # Emit status that we're about to start the orchestrator
            if hasattr(self.display, "_emit"):
                self.display._emit("preparation_status", {"status": "Connecting to agents...", "detail": "Initializing streams"})

            async for chunk in orchestrator.chat_simple(question):
                # Check if user requested quit (pressed 'q' in Rich display)
                if self.display and hasattr(self.display, "_user_quit_requested") and self.display._user_quit_requested:
                    # User pressed 'q' - cancel current turn, not entire session
                    user_quit = True
                    raise CancellationRequested(partial_saved=False)

                # Check if Ctrl+C was pressed (cancellation manager flag)
                if hasattr(orchestrator, "cancellation_manager") and orchestrator.cancellation_manager and orchestrator.cancellation_manager.is_cancelled:
                    user_quit = True
                    # Update display to show cancellation status before stopping
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status("⏸️ Cancelling turn...")
                    raise CancellationRequested(partial_saved=orchestrator.cancellation_manager._partial_saved)

                # Unpack legacy tuple format from orchestrator
                if isinstance(chunk, tuple):
                    if len(chunk) >= 2 and hasattr(chunk[1], "type"):
                        chunk = chunk[1]
                    elif len(chunk) >= 2:
                        from massgen.backend.base import StreamChunk as _SC

                        chunk = _SC(type=chunk[0], content=str(chunk[1]) if chunk[1] else "")

                content = getattr(chunk, "content", "") or ""
                source = getattr(chunk, "source", None)
                chunk_type_raw = getattr(chunk, "type", "")
                chunk_type = chunk_type_raw.value if hasattr(chunk_type_raw, "value") else str(chunk_type_raw) if chunk_type_raw else ""

                # Debug: Log all chunk types to trace hook_execution flow
                if chunk_type == "hook_execution":
                    from massgen.logger_config import logger as debug_logger

                    debug_logger.info(f"[CoordinationUI-DEBUG] Got hook_execution chunk! source={source}")

                # Check for phase changes and notify status bar (for interactive mode)
                if hasattr(orchestrator, "workflow_phase"):
                    current_phase = orchestrator.workflow_phase
                    if current_phase != self._last_phase:
                        old_phase = self._last_phase
                        self._last_phase = current_phase
                        # Debug log for phase changes
                        try:
                            from massgen.frontend.displays.textual_terminal_display import (
                                tui_log,
                            )

                            tui_log(f"CoordinationUI (interactive): phase changed '{old_phase}' -> '{current_phase}'")
                        except Exception:
                            pass
                        if hasattr(self.display, "notify_phase"):
                            self.display.notify_phase(current_phase)

                # Handle agent status updates
                if chunk_type == "agent_status":
                    status = getattr(chunk, "status", None)
                    if source and status:
                        self.display.update_agent_status(source, status)
                    continue

                # Phase 13.1: Handle token usage updates for status ribbon
                elif chunk_type == "token_usage_update":
                    usage = getattr(chunk, "usage", {})
                    if self.display and source and hasattr(self.display, "update_token_usage"):
                        self.display.update_token_usage(source, usage)
                    continue

                # Handle system status updates (e.g., "Initializing coordination...", "Preparing agents...")
                elif chunk_type == "system_status":
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status(content)

                    _emitter = get_event_emitter()
                    if _emitter and content:
                        _emitter.emit_system_status(content)
                    continue

                # Handle preparation status updates (for web UI progress)
                elif chunk_type == "preparation_status":
                    status = getattr(chunk, "status", None)
                    detail = getattr(chunk, "detail", "")
                    if status and hasattr(self.display, "_emit"):
                        # WebDisplay has _emit method for WebSocket broadcasts
                        self.display._emit("preparation_status", {"status": status, "detail": detail})
                    continue

                # Filter out debug chunks from display
                elif chunk_type == "debug":
                    # Log debug info but don't display it
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Handle cancelled chunk from orchestrator (e.g., during final presentation)
                elif chunk_type == "cancelled":
                    user_quit = True
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status("⏸️ Cancelling turn...")
                    partial_saved = orchestrator.cancellation_manager._partial_saved if hasattr(orchestrator, "cancellation_manager") and orchestrator.cancellation_manager else False
                    raise CancellationRequested(partial_saved=partial_saved)

                # Filter out tool status chunks - display via agent panel instead of console
                elif chunk_type in ("mcp_status", "custom_tool_status"):
                    # Let the display handle tool status via agent panel
                    # source may be agent_id or tool name (e.g., "mcp_mcp__filesystem__write_file")
                    target_agent = source if source in self.agent_ids else None
                    if not target_agent and self.agent_ids:
                        target_agent = self.agent_ids[0]
                    if target_agent:
                        self.display.update_agent_content(
                            target_agent,
                            content,
                            "tool",
                            tool_call_id=chunk.tool_call_id,
                        )
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Display compression status - show in agent panel
                elif chunk_type == "compression_status":
                    target_agent = source if source in self.agent_ids else None
                    if not target_agent and self.agent_ids:
                        target_agent = self.agent_ids[0]
                    if target_agent:
                        self.display.update_agent_content(target_agent, content, "tool")
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Handle hook execution events - route to display (interactive mode)
                elif chunk_type == "hook_execution":
                    hook_info = getattr(chunk, "hook_info", None)
                    tool_call_id = getattr(chunk, "tool_call_id", None)
                    from massgen.logger_config import logger as hook_logger

                    hook_logger.info(
                        f"[CoordinationUI-interactive] hook_execution chunk received: source={source}, "
                        f"tool_call_id={tool_call_id}, has_hook_info={hook_info is not None}, "
                        f"has_display={self.display is not None}, "
                        f"display_has_method={hasattr(self.display, 'update_hook_execution') if self.display else False}",
                    )
                    if self.display and source and hook_info:
                        if hasattr(self.display, "update_hook_execution"):
                            hook_logger.info("[CoordinationUI-interactive] Calling display.update_hook_execution")
                            self.display.update_hook_execution(source, tool_call_id, hook_info)
                        else:
                            hook_logger.warning("[CoordinationUI-interactive] display missing update_hook_execution method")
                    # Only emit hook events that have meaningful content (injection or non-allow decision)
                    if hook_info:
                        _decision = hook_info.get("decision", "allow") if isinstance(hook_info, dict) else "allow"
                        _has_injection = bool(hook_info.get("injection_content")) if isinstance(hook_info, dict) else False
                        if _decision != "allow" or _has_injection:
                            _emitter = get_event_emitter()
                            if _emitter:
                                _emitter.emit_hook_execution(tool_call_id, hook_info, agent_id=source)
                    if self.logger:
                        self.logger.log_chunk(source, str(hook_info), chunk_type)
                    continue
                # builtin_tool_results handling removed - now handled as simple content

                # Handle reasoning streams
                elif chunk_type in [
                    "reasoning",
                    "reasoning_done",
                    "reasoning_summary",
                    "reasoning_summary_done",
                ]:
                    if source:
                        reasoning_content = ""
                        if chunk_type == "reasoning":
                            # Stream reasoning delta as thinking content
                            reasoning_delta = getattr(chunk, "reasoning_delta", "")
                            if reasoning_delta:
                                # reasoning_content = reasoning_delta
                                reasoning_content = self._process_reasoning_content(chunk_type, reasoning_delta, source)
                        elif chunk_type == "reasoning_done":
                            # Complete reasoning text
                            reasoning_text = getattr(chunk, "reasoning_text", "")
                            if reasoning_text:
                                reasoning_content = f"\n🧠 [Reasoning Complete]\n{reasoning_text}\n"
                            else:
                                reasoning_content = "\n🧠 [Reasoning Complete]\n"

                            # Reset flag using helper method
                            self._process_reasoning_content(chunk_type, reasoning_content, source)

                            # Mark summary as complete - next summary can get a prefix
                            reasoning_active_key = "_reasoning_active"
                            if hasattr(self, reasoning_active_key):
                                delattr(self, reasoning_active_key)

                        elif chunk_type == "reasoning_summary":
                            # Stream reasoning summary delta
                            summary_delta = getattr(chunk, "reasoning_summary_delta", "")
                            if summary_delta:
                                reasoning_content = self._process_reasoning_summary(chunk_type, summary_delta, source)
                        elif chunk_type == "reasoning_summary_done":
                            # Complete reasoning summary
                            summary_text = getattr(chunk, "reasoning_summary_text", "")
                            if summary_text:
                                reasoning_content = f"\n📋 [Reasoning Summary Complete]\n{summary_text}\n"

                            # Reset flag using helper method
                            self._process_reasoning_summary(chunk_type, "", source)

                            # Mark summary as complete - next summary can get a prefix
                            summary_active_key = f"_summary_active_{source}"
                            if hasattr(self, summary_active_key):
                                delattr(self, summary_active_key)

                        if reasoning_content:
                            # Display reasoning as thinking content
                            self.display.update_agent_content(source, reasoning_content, "thinking")
                            if self.logger:
                                self.logger.log_agent_content(source, reasoning_content, "reasoning")
                    continue

                # Handle coordination chunk types (restart_banner, restart_required, agent_restart, final_presentation_start)
                if self._handle_coordination_chunk(chunk_type, chunk, content, orchestrator):
                    continue

                # Reset reasoning prefix state when final presentation starts (legacy fallback)
                if chunk_type == "status" and "presenting final answer" in content:
                    self._reset_summary_active_flags()

                # Handle post-evaluation content streaming
                # Event emission is handled by the orchestrator; coordination_ui
                # only routes content to the display layer.
                if source and content and chunk_type == "content":
                    # Check if we're in post-evaluation
                    if hasattr(self, "_in_post_evaluation") and self._in_post_evaluation:
                        if self.display and hasattr(self.display, "show_post_evaluation_content"):
                            self.display.show_post_evaluation_content(content, source)
                        # Content has been routed to post-eval panel, skip regular processing
                        continue

                # Track selected agent for post-evaluation
                if content and "🏆 Selected Agent:" in content:
                    import re

                    match = re.search(r"🏆 Selected Agent: (\S+)", content)
                    if match:
                        self._post_eval_winner = match.group(1)

                # Detect post-evaluation start
                if chunk_type == "status" and "Post-evaluation" in content:
                    self._in_post_evaluation = True
                    if self.display and hasattr(self.display, "_routing_to_post_eval_card"):
                        self.display._routing_to_post_eval_card = True

                # Detect post-evaluation completion and show footer
                if chunk_type == "status" and hasattr(self, "_in_post_evaluation") and self._in_post_evaluation:
                    if "Evaluation complete" in content or "Restart requested" in content:
                        self._in_post_evaluation = False
                        if self.display and hasattr(self.display, "_routing_to_post_eval_card"):
                            self.display._routing_to_post_eval_card = False
                        winner = getattr(self, "_post_eval_winner", None) or source
                        if self.display and hasattr(self.display, "end_post_evaluation_content"):
                            self.display.end_post_evaluation_content(winner)

                if content:
                    full_response += content

                    # Log chunk
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)

                    # Process content by source
                    # Bug 2 fix: Display-level flag prevents timeline routing, so no check needed here
                    await self._process_content(source, content, chunk_type)

            # Flush agent content buffers BEFORE processing final answer
            # This ensures any streamed content reaches the display before we complete
            try:
                if hasattr(self, "_agent_content_buffers") and self._agent_content_buffers:
                    await self._flush_agent_content_buffers()
            except asyncio.CancelledError:
                pass

            # Get final presentation content from orchestrator state
            # Note: With restart feature, get_final_presentation is called INSIDE the orchestrator
            # during _present_final_answer, so chunks already came through the main stream above.
            # We just need to retrieve the final result for return value.
            status = orchestrator.get_status()
            vote_results = status.get("vote_results", {})
            selected_agent = status.get("selected_agent", "")

            # Get the final presentation content from orchestrator state
            orchestrator_final_answer = None
            if hasattr(orchestrator, "_final_presentation_content") and orchestrator._final_presentation_content:
                orchestrator_final_answer = orchestrator._final_presentation_content.strip()
            elif selected_agent and hasattr(orchestrator, "agent_states") and selected_agent in orchestrator.agent_states:
                # Fall back to stored answer if no final presentation content
                stored_answer = orchestrator.agent_states[selected_agent].answer
                if stored_answer:
                    orchestrator_final_answer = stored_answer.strip()

            # Check for review rework signal from orchestrator
            self._check_and_dispatch_rework_signal(orchestrator)

            # Use orchestrator's clean answer or fall back to full response
            final_result = orchestrator_final_answer if orchestrator_final_answer else full_response

            # Ensure display shows final answer even if streaming chunks were filtered
            # This applies to all display types that have show_final_answer method
            # Only show if we have a valid selected agent (don't create "Unknown" files)
            if hasattr(self.display, "show_final_answer") and not self._final_answer_shown and selected_agent:
                display_answer = (final_result or "").strip()
                if display_answer:
                    self._final_answer_shown = True
                    self.display.show_final_answer(
                        display_answer,
                        vote_results=vote_results,
                        selected_agent=selected_agent,
                    )

            # Finalize session
            if self.logger:
                session_info = self.logger.finalize_session(
                    final_result if "final_result" in locals() else (final_answer if "final_answer" in locals() else ""),
                    success=True,
                )
                print(f"\U0001f4be Session log: {session_info['filename']}")
                print(f"\u23f1\ufe0f  Duration: {session_info['duration']:.1f}s | Chunks: {session_info['total_chunks']} | Events: {session_info['orchestrator_events']}")

            return final_result

        except CancellationRequested:
            # User pressed 'q' to cancel turn - propagate up to CLI
            # Don't mark as failed - this is a soft cancellation
            if self.logger:
                self.logger.finalize_session("Turn cancelled by user", success=True)
            raise
        except SystemExit:
            # Hard exit requested - cleanup and exit gracefully
            if self.logger:
                self.logger.finalize_session("User quit", success=True)
            # Cleanup agent backends
            if hasattr(orchestrator, "agents"):
                for agent_id, agent in orchestrator.agents.items():
                    if hasattr(agent.backend, "reset_state"):
                        try:
                            await agent.backend.reset_state()
                        except Exception:
                            pass
            raise
        except Exception:
            if self.logger:
                self.logger.finalize_session("", success=False)
            raise
        finally:
            # Wait for any pending timeout task to complete before cleanup
            # Wrap in try-except to handle cancellation gracefully (e.g., when user presses 'q')
            if hasattr(self, "_answer_timeout_task") and self._answer_timeout_task:
                try:
                    # Give the task a chance to complete
                    await asyncio.wait_for(self._answer_timeout_task, timeout=1.0)
                except (TimeoutError, asyncio.CancelledError):
                    # If it takes too long or was cancelled, force flush
                    try:
                        if hasattr(self, "_answer_buffer") and self._answer_buffer and not self._final_answer_shown:
                            await self._flush_final_answer()
                    except asyncio.CancelledError:
                        pass  # Silently handle cancellation
                    try:
                        self._answer_timeout_task.cancel()
                    except Exception:
                        pass

            # Final check to flush any remaining buffered answer
            try:
                if hasattr(self, "_answer_buffer") and self._answer_buffer and not self._final_answer_shown:
                    await self._flush_final_answer()
            except asyncio.CancelledError:
                pass  # Silently handle cancellation

            # Flush any remaining agent content buffers
            try:
                if hasattr(self, "_agent_content_buffers") and self._agent_content_buffers:
                    await self._flush_agent_content_buffers()
            except asyncio.CancelledError:
                pass  # Silently handle cancellation

            # Small delay to ensure display updates are processed
            try:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass  # Silently handle cancellation

            # Determine if coordination completed successfully
            # Check workflow_phase to see if we're in "presenting" state (finished) vs still coordinating (restarting)
            is_finished = hasattr(orchestrator, "workflow_phase") and orchestrator.workflow_phase == "presenting"

            # Cleanup display resources (stop live, restore terminal) unless in preserve_display mode
            # In preserve_display mode (multi-turn TUI), the external driver owns the display lifecycle
            if self.display and not self.preserve_display:
                try:
                    self.display.cleanup()
                except Exception:
                    # Fallback: at minimum stop the live display
                    if hasattr(self.display, "live") and self.display.live:
                        try:
                            self.display.live.stop()
                        except Exception:
                            pass

            # Always save coordination logs - even for incomplete runs
            # This ensures we capture partial progress for debugging/analysis
            try:
                if hasattr(orchestrator, "save_coordination_logs"):
                    # Check if logs were already saved (happens in finalize_presentation for complete runs)
                    if not is_finished:
                        orchestrator.save_coordination_logs()
            except Exception as e:
                import logging

                logging.getLogger("massgen").warning(f"Failed to save coordination logs: {e}")

            if self.logger and is_finished:
                session_info = self.logger.finalize_session(
                    final_result if "final_result" in locals() else (final_answer if "final_answer" in locals() else ""),
                    success=True,
                )
                print(f"💾 Session log: {session_info['filename']}")
                print(f"⏱️  Duration: {session_info['duration']:.1f}s | Chunks: {session_info['total_chunks']} | Events: {session_info['orchestrator_events']}")

    async def coordinate_with_context(
        self,
        orchestrator,
        question: str,
        messages: list[dict[str, Any]],
        agent_ids: list[str] | None = None,
    ) -> str:
        """Coordinate agents with conversation context and visual display.

        Args:
            orchestrator: MassGen orchestrator instance
            question: Current question for coordination
            messages: Full conversation message history
            agent_ids: Optional list of agent IDs (auto-detected if not provided)

        Returns:
            Final coordinated response
        """
        from massgen.logger_config import logger as coord_logger

        coord_logger.info(f"[CoordinationUI] coordinate_with_context() method CALLED - question: {question[:50]}..., messages={len(messages)}")

        # Initialize variables that may be referenced in finally block
        selected_agent = ""
        vote_results = {}
        final_result = ""
        final_answer = ""

        # Check if this is a restart re-entry (display already prepared)
        is_restart = getattr(self, "_is_restart", False)
        if is_restart:
            self._is_restart = False

        # Reset display to ensure clean state for each coordination
        # But preserve web displays - they have their own lifecycle managed by the web server
        # Also preserve display in preserve_display mode (for multi-turn TUI)
        # Also skip cleanup on restart re-entry (display was already prepared)
        if self.display is not None and self.display_type != "web" and not self.preserve_display and not is_restart:
            self.display.cleanup()
            self.display = None

        self.orchestrator = orchestrator
        # Set bidirectional reference so orchestrator can access UI (for broadcast prompts)
        orchestrator.coordination_ui = self
        # Ensure workspace symlinks exist for the current turn/attempt log directory
        if hasattr(orchestrator, "ensure_workspace_symlinks"):
            try:
                orchestrator.ensure_workspace_symlinks()
            except Exception as e:
                coord_logger.warning(f"[CoordinationUI] Failed to create workspace symlinks: {e}")

        # Auto-detect agent IDs if not provided
        # Sort for consistent anonymous mapping with coordination_tracker
        if agent_ids is None:
            self.agent_ids = sorted(orchestrator.agents.keys())
        else:
            self.agent_ids = sorted(agent_ids)

        # Initialize display if not provided
        if self.display is None:
            if self.display_type == "terminal":
                self.display = TerminalDisplay(self.agent_ids, **self.config)
            elif self.display_type == "simple":
                self.display = SimpleDisplay(self.agent_ids, **self.config)
            elif self.display_type == "silent":
                self.display = SilentDisplay(self.agent_ids, **self.config)
            elif self.display_type == "none":
                self.display = NoneDisplay(self.agent_ids, **self.config)
            elif self.display_type == "rich_terminal":
                if not is_rich_available():
                    print("⚠️  Rich library not available. Falling back to terminal display.")
                    print("   Install with: pip install rich")
                    self.display = TerminalDisplay(self.agent_ids, **self.config)
                else:
                    self.display = RichTerminalDisplay(self.agent_ids, **self.config)
            elif self.display_type == "textual_terminal":
                if not is_textual_available():
                    print("⚠️  Textual library not available. Falling back to terminal display.")
                    print("   Install with: pip install textual")
                    self.display = TerminalDisplay(self.agent_ids, **self.config)
                else:
                    # Build agent_models dict for welcome screen
                    agent_models = {}
                    for agent_id, agent in orchestrator.agents.items():
                        if hasattr(agent, "backend") and hasattr(agent.backend, "model"):
                            agent_models[agent_id] = agent.backend.model
                        elif hasattr(agent, "config") and hasattr(agent.config, "backend_params"):
                            agent_models[agent_id] = agent.config.backend_params.get("model", "")
                    config_with_models = {**self.config, "agent_models": agent_models}
                    self.display = TextualTerminalDisplay(self.agent_ids, **config_with_models)
            elif self.display_type == "web":
                # WebDisplay must be passed in from the web server with broadcast configured
                if self.display is None:
                    raise ValueError(
                        "WebDisplay must be passed to CoordinationUI when using " "display_type='web'. Create it via the web server.",
                    )
                # Display already set - just use it
            else:
                raise ValueError(f"Unknown display type: {self.display_type}")

        # Pass orchestrator reference to display for backend info
        self.display.orchestrator = orchestrator

        # Set up subagent spawn callbacks AFTER display is initialized
        # so the callback can access the display for TUI notifications
        if hasattr(orchestrator, "setup_subagent_spawn_callbacks"):
            orchestrator.setup_subagent_spawn_callbacks()

        # Permissions: when a real interactive TUI exists, route per-tool `ask`
        # decisions to the approval MODAL (swapping out the automation-policy provider
        # each agent's coordinator was created with). Automation/headless keeps Policy.
        self._install_interactive_approval_provider(orchestrator)

        # Start lightweight event-driven agent output writer
        from massgen.frontend.agent_output_writer import create_agent_output_writer

        self._agent_output_writer = create_agent_output_writer(self.agent_ids)

        # Initialize logger and display with context info
        log_filename = None
        if self.logger:
            # Add context info to session initialization
            context_info = f"(with {len(messages)//2} previous exchanges)" if len(messages) > 1 else ""
            session_question = f"{question} {context_info}"
            log_filename = self.logger.initialize_session(session_question, self.agent_ids)
            monitoring = self.logger.get_monitoring_commands()
            print(f"📁 Real-time log: {log_filename}")
            print(f"💡 Monitor with: {monitoring['tail']}")
            print()

        self.display.initialize(question, log_filename)

        # Reset quit flag for new turn (allows 'q' to cancel this turn)
        if hasattr(self.display, "reset_quit_request"):
            self.display.reset_quit_request()

        # Initialize variables to avoid reference before assignment error in finally block
        selected_agent = None
        vote_results = {}
        orchestrator_final_answer = None
        user_quit = False  # Track if user quit

        try:
            # Process coordination stream with conversation context
            full_response = ""
            final_answer = ""

            # Use the orchestrator's chat method with full message context
            async for chunk in orchestrator.chat(messages):
                # Check if user requested quit (pressed 'q' in Rich display)
                if self.display and hasattr(self.display, "_user_quit_requested") and self.display._user_quit_requested:
                    # User pressed 'q' - cancel current turn, not entire session
                    user_quit = True
                    raise CancellationRequested(partial_saved=False)

                # Check if Ctrl+C was pressed (cancellation manager flag)
                if hasattr(orchestrator, "cancellation_manager") and orchestrator.cancellation_manager and orchestrator.cancellation_manager.is_cancelled:
                    user_quit = True
                    # Update display to show cancellation status before stopping
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status("⏸️ Cancelling turn...")
                    raise CancellationRequested(partial_saved=orchestrator.cancellation_manager._partial_saved)

                # Unpack legacy tuple format from orchestrator
                if isinstance(chunk, tuple):
                    if len(chunk) >= 2 and hasattr(chunk[1], "type"):
                        chunk = chunk[1]
                    elif len(chunk) >= 2:
                        from massgen.backend.base import StreamChunk as _SC

                        chunk = _SC(type=chunk[0], content=str(chunk[1]) if chunk[1] else "")

                content = getattr(chunk, "content", "") or ""
                source = getattr(chunk, "source", None)
                chunk_type_raw = getattr(chunk, "type", "")
                chunk_type = chunk_type_raw.value if hasattr(chunk_type_raw, "value") else str(chunk_type_raw) if chunk_type_raw else ""

                # Handle agent status updates
                if chunk_type == "agent_status":
                    status = getattr(chunk, "status", None)
                    if source and status:
                        self.display.update_agent_status(source, status)
                    continue

                # Phase 13.1: Handle token usage updates for status ribbon
                elif chunk_type == "token_usage_update":
                    usage = getattr(chunk, "usage", {})
                    if self.display and source and hasattr(self.display, "update_token_usage"):
                        self.display.update_token_usage(source, usage)
                    continue

                # Handle system status updates (e.g., "Initializing coordination...", "Preparing agents...")
                elif chunk_type == "system_status":
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status(content)

                    _emitter = get_event_emitter()
                    if _emitter and content:
                        _emitter.emit_system_status(content)
                    continue

                # Handle preparation status updates (for web UI progress)
                elif chunk_type == "preparation_status":
                    status = getattr(chunk, "status", None)
                    detail = getattr(chunk, "detail", "")
                    if status and hasattr(self.display, "_emit"):
                        # WebDisplay has _emit method for WebSocket broadcasts
                        self.display._emit("preparation_status", {"status": status, "detail": detail})
                    continue

                # Filter out debug chunks from display
                elif chunk_type == "debug":
                    # Log debug info but don't display it
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Handle cancelled chunk from orchestrator (e.g., during final presentation)
                elif chunk_type == "cancelled":
                    user_quit = True
                    if self.display and hasattr(self.display, "update_system_status"):
                        self.display.update_system_status("⏸️ Cancelling turn...")
                    partial_saved = orchestrator.cancellation_manager._partial_saved if hasattr(orchestrator, "cancellation_manager") and orchestrator.cancellation_manager else False
                    raise CancellationRequested(partial_saved=partial_saved)

                # Filter out tool status chunks - display via agent panel instead of console
                elif chunk_type in ("mcp_status", "custom_tool_status"):
                    # Let the display handle tool status via agent panel
                    # source may be agent_id or tool name (e.g., "mcp_mcp__filesystem__write_file")
                    target_agent = source if source in self.agent_ids else None
                    if not target_agent and self.agent_ids:
                        target_agent = self.agent_ids[0]
                    if target_agent:
                        self.display.update_agent_content(
                            target_agent,
                            content,
                            "tool",
                            tool_call_id=chunk.tool_call_id,
                        )
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Display compression status - show in agent panel
                elif chunk_type == "compression_status":
                    target_agent = source if source in self.agent_ids else None
                    if not target_agent and self.agent_ids:
                        target_agent = self.agent_ids[0]
                    if target_agent:
                        self.display.update_agent_content(target_agent, content, "tool")
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # builtin_tool_results handling removed - now handled as simple content

                # Handle reasoning streams
                elif chunk_type in [
                    "reasoning",
                    "reasoning_done",
                    "reasoning_summary",
                    "reasoning_summary_done",
                ]:
                    if source:
                        reasoning_content = ""
                        if chunk_type == "reasoning":
                            # Stream reasoning delta as thinking content
                            reasoning_delta = getattr(chunk, "reasoning_delta", "")
                            if reasoning_delta:
                                # reasoning_content = reasoning_delta
                                reasoning_content = self._process_reasoning_content(chunk_type, reasoning_delta, source)
                        elif chunk_type == "reasoning_done":
                            # Complete reasoning text
                            reasoning_text = getattr(chunk, "reasoning_text", "")
                            if reasoning_text:
                                reasoning_content = f"\n🧠 [Reasoning Complete]\n{reasoning_text}\n"
                            else:
                                reasoning_content = "\n🧠 [Reasoning Complete]\n"

                            # Reset flag using helper method
                            self._process_reasoning_content(chunk_type, reasoning_content, source)

                            # Mark summary as complete - next summary can get a prefix
                            reasoning_active_key = "_reasoning_active"
                            if hasattr(self, reasoning_active_key):
                                delattr(self, reasoning_active_key)
                        elif chunk_type == "reasoning_summary":
                            # Stream reasoning summary delta
                            summary_delta = getattr(chunk, "reasoning_summary_delta", "")
                            if summary_delta:
                                reasoning_content = self._process_reasoning_summary(chunk_type, summary_delta, source)
                        elif chunk_type == "reasoning_summary_done":
                            # Complete reasoning summary
                            summary_text = getattr(chunk, "reasoning_summary_text", "")
                            if summary_text:
                                reasoning_content = f"\n📋 [Reasoning Summary Complete]\n{summary_text}\n"

                            # Reset flag using helper method
                            self._process_reasoning_summary(chunk_type, "", source)

                            # Mark summary as complete - next summary can get a prefix
                            summary_active_key = f"_summary_active_{source}"
                            if hasattr(self, summary_active_key):
                                delattr(self, summary_active_key)

                        if reasoning_content:
                            # Display reasoning as thinking content
                            self.display.update_agent_content(source, reasoning_content, "thinking")
                            if self.logger:
                                self.logger.log_agent_content(source, reasoning_content, "reasoning")
                    continue

                # Handle coordination chunk types (restart_banner, restart_required, agent_restart, final_presentation_start)
                if self._handle_coordination_chunk(chunk_type, chunk, content, orchestrator):
                    continue

                # Reset reasoning prefix state when final presentation starts (legacy fallback)
                if chunk_type == "status" and "presenting final answer" in content:
                    self._reset_summary_active_flags()

                # Handle post-evaluation content streaming
                # Event emission is handled by the orchestrator; coordination_ui
                # only routes content to the display layer.
                if source and content and chunk_type == "content":
                    # Check if we're in post-evaluation
                    if hasattr(self, "_in_post_evaluation") and self._in_post_evaluation:
                        if self.display and hasattr(self.display, "show_post_evaluation_content"):
                            self.display.show_post_evaluation_content(content, source)
                        # Content has been routed to post-eval panel, skip regular processing
                        continue

                # Track selected agent for post-evaluation
                if content and "🏆 Selected Agent:" in content:
                    import re

                    match = re.search(r"🏆 Selected Agent: (\S+)", content)
                    if match:
                        self._post_eval_winner = match.group(1)

                # Detect post-evaluation start
                if chunk_type == "status" and "Post-evaluation" in content:
                    self._in_post_evaluation = True
                    if self.display and hasattr(self.display, "_routing_to_post_eval_card"):
                        self.display._routing_to_post_eval_card = True

                # Detect post-evaluation completion and show footer
                if chunk_type == "status" and hasattr(self, "_in_post_evaluation") and self._in_post_evaluation:
                    if "Evaluation complete" in content or "Restart requested" in content:
                        self._in_post_evaluation = False
                        if self.display and hasattr(self.display, "_routing_to_post_eval_card"):
                            self.display._routing_to_post_eval_card = False
                        winner = getattr(self, "_post_eval_winner", None) or source
                        if self.display and hasattr(self.display, "end_post_evaluation_content"):
                            self.display.end_post_evaluation_content(winner)

                if content:
                    full_response += content

                    # Log chunk
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)

                    # Process content by source
                    # Bug 2 fix: Display-level flag prevents timeline routing, so no check needed here
                    await self._process_content(source, content, chunk_type)

            # Flush agent content buffers BEFORE processing final answer
            # This ensures any streamed content reaches the display before we complete
            try:
                if hasattr(self, "_agent_content_buffers") and self._agent_content_buffers:
                    await self._flush_agent_content_buffers()
            except asyncio.CancelledError:
                pass

            # Display vote results and get final presentation
            status = orchestrator.get_status()
            vote_results = status.get("vote_results", {})
            selected_agent = status.get("selected_agent")

            # Ensure selected_agent is not None to prevent UnboundLocalError
            if selected_agent is None:
                selected_agent = ""

            # if vote_results.get('vote_counts'):
            #     self._display_vote_results(vote_results)
            #     # Allow time for voting results to be visible
            #     import time
            #     time.sleep(1.0)

            # Get final presentation content from orchestrator state
            # Note: With restart feature, get_final_presentation is called INSIDE the orchestrator
            # during _present_final_answer, so chunks already came through the main stream above.
            # We just need to retrieve the final result for return value.

            # Get the final answer from orchestrator's stored state
            orchestrator_final_answer = None
            if hasattr(orchestrator, "_final_presentation_content") and orchestrator._final_presentation_content:
                orchestrator_final_answer = orchestrator._final_presentation_content.strip()
            elif selected_agent and hasattr(orchestrator, "agent_states") and selected_agent in orchestrator.agent_states:
                # Fall back to stored answer if no final presentation content
                stored_answer = orchestrator.agent_states[selected_agent].answer
                if stored_answer:
                    orchestrator_final_answer = stored_answer.strip()

            # Check for review rework signal from orchestrator
            self._check_and_dispatch_rework_signal(orchestrator)

            # Use orchestrator's clean answer or fall back to full response
            final_result = orchestrator_final_answer if orchestrator_final_answer else full_response

            # Ensure display shows final answer even if streaming chunks were filtered
            # This applies to all display types that have show_final_answer method
            # Only show if we have a valid selected agent (don't create "Unknown" files)
            if hasattr(self.display, "show_final_answer") and not self._final_answer_shown and selected_agent:
                display_answer = (final_result or "").strip()
                if display_answer:
                    self._final_answer_shown = True
                    self.display.show_final_answer(
                        display_answer,
                        vote_results=vote_results,
                        selected_agent=selected_agent,
                    )

            # Finalize session
            if self.logger:
                session_info = self.logger.finalize_session(
                    final_result if "final_result" in locals() else (final_answer if "final_answer" in locals() else ""),
                    success=True,
                )
                print(f"\U0001f4be Session log: {session_info['filename']}")
                print(f"\u23f1\ufe0f  Duration: {session_info['duration']:.1f}s | Chunks: {session_info['total_chunks']} | Events: {session_info['orchestrator_events']}")

            return final_result

        except CancellationRequested:
            # User pressed 'q' or Ctrl+C to cancel turn - propagate up to CLI
            # Don't mark as failed - this is a soft cancellation
            if self.logger:
                self.logger.finalize_session("Turn cancelled by user", success=True)
            raise
        except SystemExit:
            # Hard exit requested - cleanup and exit gracefully
            if self.logger:
                self.logger.finalize_session("User quit", success=True)
            # Cleanup agent backends
            if hasattr(orchestrator, "agents"):
                for agent_id, agent in orchestrator.agents.items():
                    if hasattr(agent.backend, "reset_state"):
                        try:
                            await agent.backend.reset_state()
                        except Exception:
                            pass
            raise
        except Exception:
            if self.logger:
                self.logger.finalize_session("", success=False)
            raise
        finally:
            # Wait for any pending timeout task to complete before cleanup
            # Wrap in try-except to handle cancellation gracefully (e.g., when user presses 'q')
            if hasattr(self, "_answer_timeout_task") and self._answer_timeout_task:
                try:
                    # Give the task a chance to complete
                    await asyncio.wait_for(self._answer_timeout_task, timeout=1.0)
                except (TimeoutError, asyncio.CancelledError):
                    # If it takes too long or was cancelled, force flush
                    try:
                        if hasattr(self, "_answer_buffer") and self._answer_buffer and not self._final_answer_shown:
                            await self._flush_final_answer()
                    except asyncio.CancelledError:
                        pass  # Silently handle cancellation
                    try:
                        self._answer_timeout_task.cancel()
                    except Exception:
                        pass

            # Final check to flush any remaining buffered answer
            try:
                if hasattr(self, "_answer_buffer") and self._answer_buffer and not self._final_answer_shown:
                    await self._flush_final_answer()
            except asyncio.CancelledError:
                pass  # Silently handle cancellation

            # Flush any remaining agent content buffers
            try:
                if hasattr(self, "_agent_content_buffers") and self._agent_content_buffers:
                    await self._flush_agent_content_buffers()
            except asyncio.CancelledError:
                pass  # Silently handle cancellation

            # Small delay to ensure display updates are processed
            try:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass  # Silently handle cancellation

            # Determine if coordination completed successfully
            is_finished = hasattr(orchestrator, "workflow_phase") and orchestrator.workflow_phase == "presenting"

            # Cleanup display resources (stop live, restore terminal) unless in preserve_display mode
            # In preserve_display mode (multi-turn TUI), the external driver owns the display lifecycle
            if self.display and not self.preserve_display:
                try:
                    self.display.cleanup()
                except Exception:
                    # Fallback: at minimum stop the live display
                    if hasattr(self.display, "live") and self.display.live:
                        try:
                            self.display.live.stop()
                        except Exception:
                            pass

            # Always save coordination logs - even for incomplete runs
            # This ensures we capture partial progress for debugging/analysis
            try:
                if hasattr(orchestrator, "save_coordination_logs"):
                    # Check if logs were already saved (happens in finalize_presentation for complete runs)
                    if not is_finished:
                        orchestrator.save_coordination_logs()
            except Exception as e:
                import logging

                logging.getLogger("massgen").warning(f"Failed to save coordination logs: {e}")

    def _display_vote_results(self, vote_results: dict[str, Any]):
        """Display voting results in a formatted table."""
        print("\n🗳️  VOTING RESULTS")
        print("=" * 50)

        vote_counts = vote_results.get("vote_counts", {})
        voter_details = vote_results.get("voter_details", {})
        winner = vote_results.get("winner")
        is_tie = vote_results.get("is_tie", False)

        # Display vote counts
        if vote_counts:
            print("\n📊 Vote Count:")
            for agent_id, count in sorted(vote_counts.items(), key=lambda x: x[1], reverse=True):
                winner_mark = "🏆" if agent_id == winner else "  "
                tie_mark = " (tie-broken)" if is_tie and agent_id == winner else ""
                print(f"   {winner_mark} {agent_id}: {count} vote{'s' if count != 1 else ''}{tie_mark}")

        # Display voter details
        if voter_details:
            print("\n🔍 Vote Details:")
            for voted_for, voters in voter_details.items():
                print(f"   → {voted_for}:")
                for voter_info in voters:
                    voter = voter_info["voter"]
                    reason = voter_info["reason"]
                    print(f'     • {voter}: "{reason}"')

        # Display tie-breaking info
        if is_tie:
            print("\n⚖️  Tie broken by agent registration order (orchestrator setup order)")

        # Display summary stats
        total_votes = vote_results.get("total_votes", 0)
        agents_voted = vote_results.get("agents_voted", 0)
        print(f"\n📈 Summary: {agents_voted}/{total_votes} agents voted")
        print("=" * 50)

    async def _process_content(self, source: str | None, content: str, chunk_type: str = "thinking"):
        """Process content from coordination stream."""
        # Handle agent content
        if source in self.agent_ids:
            await self._process_agent_content(source, content, chunk_type)

        # Handle orchestrator content
        elif source in ["coordination_hub", "orchestrator"] or source is None:
            await self._process_orchestrator_content(content)

        # Capture coordination events from any source (orchestrator or agents)
        if any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]):
            clean_line = content.replace("**", "").replace("##", "").strip()
            if clean_line and not any(
                skip in clean_line
                for skip in [
                    "result ignored",
                    "Starting",
                    "Agents Coordinating",
                    "Coordinating agents, please wait",
                ]
            ):
                event = f"🔄 {source}: {clean_line}" if source and source not in ["coordination_hub", "orchestrator"] else f"🔄 {clean_line}"
                self.display.add_orchestrator_event(event)
                if self.logger:
                    self.logger.log_orchestrator_event(event)

    async def _process_agent_content(self, agent_id: str, content: str, chunk_type: str = "thinking"):
        """Process content from a specific agent.

        Uses buffered filtering to handle streaming: small chunks are accumulated
        until we see a newline or have enough content to check for workspace JSON.
        """
        # Store chunk_type for this agent's buffer
        if not hasattr(self, "_agent_chunk_types"):
            self._agent_chunk_types = {}
        self._agent_chunk_types[agent_id] = chunk_type
        # Filter coordination messages that duplicate tool cards/notifications
        # These are yielded by orchestrator when processing workspace tool calls
        if "Providing answer:" in content or "🗳️ Voting for" in content:
            return

        # Update agent status - if agent is streaming content, they're working
        # But don't override "completed" status
        current_status = self.display.get_agent_status(agent_id)
        if current_status not in ["working", "completed"]:
            self.display.update_agent_status(agent_id, "working")

        # Initialize buffer for this agent if needed
        if agent_id not in self._agent_content_buffers:
            self._agent_content_buffers[agent_id] = ""

        # Add content to buffer
        self._agent_content_buffers[agent_id] += content

        # Check if we should process the buffer:
        # Keep accumulating until we can reliably determine if there's workspace JSON
        buffer = self._agent_content_buffers[agent_id]
        buffer_len = len(buffer)

        # Check if buffer might contain workspace JSON (look at the WHOLE buffer)
        # Also detect partial JSON patterns that indicate workspace action is starting
        has_workspace_pattern = (
            '"action_type"' in buffer
            or '"answer_data"' in buffer
            or '"action": "new_answer"' in buffer
            or '"action": "vote"' in buffer
            or '"action":' in buffer
            or '"action"' in buffer  # Partial JSON key
            or "```json" in buffer  # JSON key without colon yet
        )

        if has_workspace_pattern:
            # Buffer has workspace JSON patterns - wait for it to complete
            open_braces = buffer.count("{") - buffer.count("}")
            open_brackets = buffer.count("[") - buffer.count("]")

            # JSON is complete when braces are balanced AND we have closing braces
            json_complete = open_braces == 0 and open_brackets == 0 and "}" in buffer

            # For code fences, need both opening and closing
            if "```json" in buffer:
                fence_count = buffer.count("```")
                json_complete = fence_count >= 2

            if not json_complete and buffer_len < 2000:
                # JSON still incomplete, keep buffering
                return

        # No workspace patterns, or JSON is complete - check flush conditions
        # For regular content (no JSON patterns), flush more aggressively for streaming UX
        if not has_workspace_pattern:
            ends_with_sentence = buffer.rstrip().endswith((".", "!", "?", ":", "\n"))
            should_flush = buffer_len >= 80 or (ends_with_sentence and buffer_len >= 2)

            if not should_flush:
                return

        # Process the buffered content
        self._agent_content_buffers[agent_id] = ""

        # Use unified extraction to handle all workspace JSON formats:
        # - Pure JSON: {"action_type": ...}
        # - Code fence: ```json\n{...}\n```
        # - Code fence with text: "Here's my vote:\n```json\n{...}\n```"
        # - Embedded JSON: "I'll vote for Agent 1. {"action_type": ...}"
        extraction_result = ContentNormalizer.extract_workspace_json(buffer)
        if extraction_result:
            json_str, text_before, text_after = extraction_result
            workspace_action = self._parse_workspace_action(json_str)

            if workspace_action:
                action_type, params = workspace_action

                # For new_answer and vote actions:
                # - Don't emit text_before (content is in JSON, shown via answer card/vote notification)
                # - Don't create tool card here (send_new_answer/vote display will create it)
                # This prevents duplicate content and duplicate tool cards
                if action_type in ("new_answer", "vote"):
                    # Just log and return - orchestrator's send_new_answer/vote will handle display
                    if self.logger:
                        tool_msg = f"🔧 Calling workspace/{action_type}"
                        if params:
                            tool_msg += f" {params}"
                        self.logger.log_agent_content(agent_id, tool_msg, "tool")
                    # Emit structured event for the pipeline

                    _emitter = get_event_emitter()
                    if _emitter:
                        _emitter.emit_workspace_action(action_type, params, agent_id=agent_id)
                    return

                # For other workspace actions, emit text_before and create tool card
                if text_before and not ContentNormalizer.is_workspace_state_content(text_before):
                    await self._emit_agent_content(agent_id, text_before, chunk_type)

                # Create tool card for the workspace action
                tool_msg = f"🔧 Calling workspace/{action_type}"
                if params:
                    tool_msg += f" {params}"
                self.display.update_agent_content(agent_id, tool_msg, "tool")
                if self.logger:
                    self.logger.log_agent_content(agent_id, tool_msg, "tool")
                # Emit structured event for the pipeline

                _emitter = get_event_emitter()
                if _emitter:
                    _emitter.emit_workspace_action(action_type, params, agent_id=agent_id)

                # Emit any text after the JSON as content (rare but possible)
                if text_after and not ContentNormalizer.is_workspace_state_content(text_after):
                    await self._emit_agent_content(agent_id, text_after, chunk_type)
                return
            else:
                # Couldn't parse the JSON, just log and skip
                if self.logger:
                    self.logger.log_agent_content(agent_id, buffer, "filtered_workflow_json")
                return

        # Filter workspace state content (CWD, File created, etc.)
        # This is internal coordination info that shouldn't be shown to users
        if ContentNormalizer.is_workspace_state_content(buffer):
            if self.logger:
                self.logger.log_agent_content(agent_id, buffer, "filtered_workspace_state")
            return

        # Emit the buffered content
        await self._emit_agent_content(agent_id, buffer, chunk_type)

    async def _emit_agent_content(self, agent_id: str, content: str, chunk_type: str = None):
        """Emit agent content to the display after filtering.

        Tool content (mcp_status, custom_tool_status) never reaches this method —
        it's intercepted earlier in the stream processing loop and routed directly
        to display.update_agent_content with content_type="tool". Structured
        TOOL_START/TOOL_COMPLETE events from the backend handle TUI tool cards.
        """
        # Get chunk_type from stored value if not provided
        if chunk_type is None:
            chunk_type = getattr(self, "_agent_chunk_types", {}).get(agent_id, "thinking")

        # Emit structured events for the unified event pipeline

        _emitter = get_event_emitter()
        if _emitter:
            if chunk_type in ("reasoning", "reasoning_done", "reasoning_summary", "reasoning_summary_done", "thinking"):
                _emitter.emit_thinking(content, agent_id=agent_id)
            elif chunk_type in ("content", "text"):
                _emitter.emit_text(content, agent_id=agent_id)
            elif chunk_type in ("status", "system_status", "backend_status"):
                _emitter.emit_status(content, agent_id=agent_id)
            elif chunk_type in ("presentation", "final_answer"):
                _emitter.emit_final_answer(content, agent_id=agent_id)

        if "🔄 Vote invalid" in content:
            self.display.update_agent_content(agent_id, content, "status")
            if self.logger:
                self.logger.log_agent_content(agent_id, content, "status")
        else:
            # Route all content through update_agent_content() so it goes through
            # the normal content pipeline (ContentNormalizer, tool cards, thinking sections, etc.)
            # Final presentation content is handled as a new round (N+1) with the same pipeline.
            self.display.update_agent_content(agent_id, content, chunk_type)
            if self.logger:
                self.logger.log_agent_content(agent_id, content, chunk_type)

    def _parse_workspace_action(self, content: str) -> tuple | None:
        """Parse workspace action from JSON content.

        Returns:
            Tuple of (action_type, params_summary) or None if parsing fails.
        """
        import json

        # Try to extract JSON from content
        # Content may have extra text before/after JSON
        json_start = content.find("{")
        json_end = content.rfind("}") + 1

        if json_start == -1 or json_end <= json_start:
            return None

        json_str = content[json_start:json_end]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Try to fix common issues like escaped newlines
            try:
                # Replace literal \n with actual newlines for parsing
                fixed = json_str.replace("\\n", "\n")
                data = json.loads(fixed)
            except json.JSONDecodeError:
                return None

        # Extract action type
        action_type = data.get("action_type") or data.get("action")
        if not action_type:
            # Check for nested structure
            if "answer_data" in data:
                action_type = data["answer_data"].get("action")
            elif "vote_data" in data:
                action_type = data["vote_data"].get("action")

        if not action_type:
            return None

        # Build params summary based on action type
        params = ""
        if action_type == "new_answer":
            # Extract answer content preview (may be nested in answer_data)
            answer_data = data.get("answer_data", data)
            content_preview = answer_data.get("content", "")
            if content_preview:
                # Truncate to first 50 chars
                preview = content_preview[:50].replace("\n", " ")
                if len(content_preview) > 50:
                    preview += "..."
                params = f'content="{preview}"'
        elif action_type == "vote":
            # Extract vote target (may be nested in vote_data)
            vote_data = data.get("vote_data", data)
            target = vote_data.get("agent_id", "") or data.get("target_agent_id", "")
            reason = vote_data.get("reason", "") or data.get("reason", "")
            if target:
                params = f"target={target}"
                if reason:
                    reason_preview = reason[:30].replace("\n", " ")
                    if len(reason) > 30:
                        reason_preview += "..."
                    params += f' reason="{reason_preview}"'

        return (action_type, params)

    async def _flush_agent_content_buffers(self):
        """Flush any remaining content in agent buffers.

        Called at the end of a coordination turn to ensure no content is lost.
        """
        for agent_id, buffer in list(self._agent_content_buffers.items()):
            if buffer.strip():
                # Check if it's pure workspace JSON - if so, convert to tool card
                if ContentNormalizer.is_workspace_tool_json(buffer):
                    workspace_action = self._parse_workspace_action(buffer)
                    if workspace_action:
                        action_type, params = workspace_action
                        tool_msg = f"🔧 Calling workspace/{action_type}"
                        if params:
                            tool_msg += f" {params}"

                        _emitter = get_event_emitter()
                        if _emitter:
                            _emitter.emit_workspace_action(action_type, params, agent_id=agent_id)
                        self.display.update_agent_content(agent_id, tool_msg, "tool")
                        if self.logger:
                            self.logger.log_agent_content(agent_id, tool_msg, "tool")
                    elif self.logger:
                        self.logger.log_agent_content(agent_id, buffer, "filtered_workflow_json")
                # Check if buffer contains embedded workspace JSON (mixed content)
                elif self._parse_workspace_action(buffer):
                    workspace_action = self._parse_workspace_action(buffer)
                    action_type, params = workspace_action
                    # Create tool card
                    tool_msg = f"🔧 Calling workspace/{action_type}"
                    if params:
                        tool_msg += f" {params}"

                    _emitter = get_event_emitter()
                    if _emitter:
                        _emitter.emit_workspace_action(action_type, params, agent_id=agent_id)
                    self.display.update_agent_content(agent_id, tool_msg, "tool")
                    if self.logger:
                        self.logger.log_agent_content(agent_id, tool_msg, "tool")
                    # Emit reasoning part if any
                    json_start = buffer.find("{")
                    if json_start > 0:
                        reasoning_part = buffer[:json_start].strip()
                        if reasoning_part and not ContentNormalizer.is_workspace_state_content(reasoning_part):
                            stored_chunk_type = getattr(self, "_agent_chunk_types", {}).get(agent_id, "content")
                            await self._emit_agent_content(agent_id, reasoning_part, stored_chunk_type)
                # Filter workspace state content (CWD, File created, etc.)
                elif ContentNormalizer.is_workspace_state_content(buffer):
                    if self.logger:
                        self.logger.log_agent_content(agent_id, buffer, "filtered_workspace_state")
                else:
                    stored_chunk_type = getattr(self, "_agent_chunk_types", {}).get(agent_id, "content")
                    await self._emit_agent_content(agent_id, buffer, stored_chunk_type)
        self._agent_content_buffers = {}

    async def _flush_final_answer(self):
        """Flush the buffered final answer after a timeout to prevent duplicate calls."""
        if self._final_answer_shown or not self._answer_buffer.strip():
            return

        # Don't create final presentation if restart is pending
        if hasattr(self.orchestrator, "restart_pending") and self.orchestrator.restart_pending:
            return

        # Don't show final answer (and inspection menu) if post-evaluation might still run
        # Only show when orchestration is TRULY finished
        if hasattr(self.orchestrator, "max_attempts"):
            post_eval_enabled = self.orchestrator.max_attempts > 1
            is_finished = hasattr(self.orchestrator, "workflow_phase") and self.orchestrator.workflow_phase == "presenting"

            # If post-eval is enabled, only show after workflow is finished
            if post_eval_enabled and not is_finished:
                return

        # Get orchestrator status for voting results and winner
        status = self.orchestrator.get_status()
        selected_agent = status.get("selected_agent")

        # Don't create file if no valid agent is selected
        if not selected_agent:
            return

        vote_results = status.get("vote_results", {})

        # Mark as shown to prevent duplicate calls
        self._final_answer_shown = True

        # Show the final answer (which includes inspection menu)
        self.display.show_final_answer(
            self._answer_buffer.strip(),
            vote_results=vote_results,
            selected_agent=selected_agent,
        )

    async def _process_orchestrator_content(self, content: str):
        """Process content from orchestrator."""
        # Filter coordination messages that duplicate tool cards/notifications
        # These are yielded by orchestrator when processing workspace tool calls
        if "Providing answer:" in content or "🗳️ Voting for" in content:
            return

        # Handle final answer - merge with voting info
        if "Final Coordinated Answer" in content:
            # Don't create event yet - wait for actual answer content to merge
            pass

        # Handle coordination events (provided answer, votes)
        elif any(marker in content for marker in ["✅", "🗳️", "🔄", "❌", "⚠️"]):
            clean_line = content.replace("**", "").replace("##", "").strip()
            if clean_line and not any(
                skip in clean_line
                for skip in [
                    "result ignored",
                    "Starting",
                    "Agents Coordinating",
                    "Coordinating agents, please wait",
                ]
            ):
                event = f"🔄 {clean_line}"
                self.display.add_orchestrator_event(event)
                if self.logger:
                    self.logger.log_orchestrator_event(event)

                # Parse vote events for status bar notification
                # Format: "🗳️ Voting for [agent_id] (options: ...) : reason"
                if "🗳️" in content and "Voting for" in content:
                    vote_match = re.search(r"Voting for \[([^\]]+)\].*?:\s*(.*)$", content)
                    if vote_match and hasattr(self.display, "notify_vote"):
                        voted_for = vote_match.group(1)
                        reason = vote_match.group(2).strip() if vote_match.group(2) else ""
                        # Get voter from orchestrator status if available
                        voter = "Agent"  # Default fallback
                        submission_round = 1  # Default fallback
                        if self.orchestrator:
                            # Try to get the agent that just voted from status
                            status = self.orchestrator.get_status()
                            # Use current agent context if available
                            if hasattr(self.orchestrator, "_current_streaming_agent"):
                                voter = self.orchestrator._current_streaming_agent
                            # Get the voter's round (0-indexed) and convert to 1-indexed
                            tracker = getattr(self.orchestrator, "coordination_tracker", None)
                            if tracker and voter != "Agent":
                                submission_round = tracker.get_agent_round(voter) + 1
                        self.display.notify_vote(voter, voted_for, reason, submission_round)

        # Handle final answer content - buffer it to prevent duplicate calls
        elif "Final Coordinated Answer" not in content and not any(
            marker in content
            for marker in [
                "✅",
                "🗳️",
                "🎯",
                "Starting",
                "Agents Coordinating",
                "🔄",
                "**",
                "result ignored",
                "restart pending",
                "🏆",  # Selected Agent banner
                "🎤",  # presenting final answer
                "🔍",  # Post-evaluation
            ]
        ):
            # Extract clean final answer content
            clean_content = content.strip()
            if clean_content and not clean_content.startswith("---") and not clean_content.startswith("*Coordinated by"):
                # Add to buffer
                if self._answer_buffer:
                    self._answer_buffer += " " + clean_content
                else:
                    self._answer_buffer = clean_content

                # Cancel previous timeout if it exists
                if self._answer_timeout_task:
                    self._answer_timeout_task.cancel()

                # Set a timeout to flush the answer (in case streaming stops)
                self._answer_timeout_task = asyncio.create_task(self._schedule_final_answer_flush())

                # Create event for this chunk but don't call show_final_answer yet
                status = self.orchestrator.get_status()
                selected_agent = status.get("selected_agent")
                vote_results = status.get("vote_results", {})
                vote_counts = vote_results.get("vote_counts", {})
                is_tie = vote_results.get("is_tie", False)

                # Only create final event for first chunk to avoid spam
                if self._answer_buffer == clean_content:  # First chunk
                    # Check if orchestrator timed out
                    orchestrator_timeout = getattr(self.orchestrator, "is_orchestrator_timeout", False)

                    if not selected_agent:
                        if orchestrator_timeout:
                            # Even with timeout, try to select agent from available votes
                            if vote_counts:
                                # Find agent with most votes
                                max_votes = max(vote_counts.values())
                                tied_agents = [agent for agent, count in vote_counts.items() if count == max_votes]
                                # Use first tied agent (following orchestrator's tie-breaking logic)
                                timeout_selected_agent = tied_agents[0] if tied_agents else None
                                if timeout_selected_agent:
                                    vote_summary = ", ".join([f"{agent}: {count}" for agent, count in vote_counts.items()])
                                    tie_info = " (tie-broken by registration order)" if len(tied_agents) > 1 else ""
                                    event = f"🎯 FINAL: {timeout_selected_agent} selected from partial votes ({vote_summary}{tie_info}) → orchestrator timeout → [buffering...]"
                                else:
                                    event = "🎯 FINAL: None selected → orchestrator timeout (no agents completed voting in time) → [buffering...]"
                            else:
                                event = "🎯 FINAL: None selected → orchestrator timeout (no agents completed voting in time) → [buffering...]"
                        else:
                            event = "🎯 FINAL: None selected → [buffering...]"
                    elif vote_counts:
                        vote_summary = ", ".join([f"{agent}: {count} vote{'s' if count != 1 else ''}" for agent, count in vote_counts.items()])
                        tie_info = " (tie-broken by registration order)" if is_tie else ""
                        timeout_info = " (despite timeout)" if orchestrator_timeout else ""
                        event = f"🎯 FINAL: {selected_agent} selected ({vote_summary}{tie_info}){timeout_info} → [buffering...]"
                    else:
                        timeout_info = " (despite timeout)" if orchestrator_timeout else ""
                        event = f"🎯 FINAL: {selected_agent} selected{timeout_info} → [buffering...]"

                    self.display.add_orchestrator_event(event)
                    if self.logger:
                        self.logger.log_orchestrator_event(event)

    async def _schedule_final_answer_flush(self):
        """Schedule the final answer flush after a delay to collect all chunks."""
        await asyncio.sleep(0.5)  # Wait 0.5 seconds for more chunks
        await self._flush_final_answer()

    def _print_with_flush(self, content: str):
        """Print content chunks directly without character-by-character flushing."""
        try:
            # Display the entire chunk immediately
            print(content, end="", flush=True)
        except Exception:
            # On any error, fallback to immediate display
            print(content, end="", flush=True)

    async def prompt_for_broadcast_response(self, broadcast_request: Any) -> Any | None:
        """Prompt human for response to a broadcast question.

        Args:
            broadcast_request: BroadcastRequest object with question details

        Returns:
            Human's response string (for simple questions) or List[StructuredResponse] (for structured questions),
            or None if skipped/timeout
        """

        # Skip human input in automation mode
        if self.config.get("automation_mode", False):
            question_preview = broadcast_request.question_text[:100] if broadcast_request.question_text else "structured questions"
            print(f"\n📢 [Automation Mode] Skipping human input for broadcast from {broadcast_request.sender_agent_id}")
            print(f"   Question: {question_preview}{'...' if len(question_preview) >= 100 else ''}\n")
            return None

        # Delegate to display if it supports broadcast prompts
        if self.display and hasattr(self.display, "prompt_for_broadcast_response"):
            return await self.display.prompt_for_broadcast_response(broadcast_request)

        # Fallback: Basic terminal implementation
        print("\n" + "=" * 70)
        print(f"📢 BROADCAST FROM {broadcast_request.sender_agent_id.upper()}")
        print("=" * 70)

        # Check if structured question
        if broadcast_request.is_structured:
            return await self._prompt_structured_fallback(broadcast_request)
        else:
            return await self._prompt_simple_fallback(broadcast_request)

    async def _prompt_simple_fallback(self, broadcast_request: Any) -> str | None:
        """Fallback terminal prompt for simple free-form questions.

        Args:
            broadcast_request: BroadcastRequest with simple question

        Returns:
            User's text response or None if skipped/timeout
        """
        print(f"\n{broadcast_request.question}\n")
        print("─" * 70)
        print("Options:")
        print("  • Type your response and press Enter")
        print("  • Press Enter alone to skip")
        print(f"  • You have {broadcast_request.timeout} seconds to respond")
        print("=" * 70)

        try:
            # Use asyncio to read input with timeout
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    input,
                    "Your response (or Enter to skip): ",
                ),
                timeout=float(broadcast_request.timeout),
            )

            response = response.strip()
            if response:
                print(f"\n✓ Response submitted: {response[:50]}{'...' if len(response) > 50 else ''}\n")
                return response
            else:
                print("\n⏭️  Skipped (no response)\n")
                return None

        except TimeoutError:
            print("\n⏱️  Timeout - no response submitted\n")
            return None
        except Exception as e:
            print(f"\n❌ Error getting response: {e}\n")
            return None

    async def _prompt_structured_fallback(self, broadcast_request: Any) -> list | None:
        """Fallback terminal prompt for structured questions with options.

        Args:
            broadcast_request: BroadcastRequest with structured questions

        Returns:
            List of StructuredResponse objects or None if skipped/timeout
        """
        from massgen.broadcast.broadcast_dataclasses import StructuredResponse

        questions = broadcast_request.structured_questions
        responses = []

        for q_idx, question in enumerate(questions):
            # Show progress for multi-question
            if len(questions) > 1:
                print(f"\n[Question {q_idx + 1} of {len(questions)}]")

            print(f"\n{question.text}\n")
            print("─" * 70)

            # Display numbered options
            print("Options:")
            for i, option in enumerate(question.options, 1):
                desc = f" - {option.description}" if option.description else ""
                print(f"  {i}. {option.label}{desc}")

            print("\n─" * 70)
            print("How to respond:")
            if question.multi_select:
                print("  • Enter numbers separated by commas (e.g., 1,3)")
            else:
                print("  • Enter a number to select an option")
            if question.allow_other:
                print("  • Type 'other: your text' for a custom answer")
            if not question.required:
                print("  • Press Enter alone to skip")
            print(f"  • Timeout: {broadcast_request.timeout} seconds")
            print("=" * 70)

            try:
                prompt_text = "Your selection: " if question.multi_select else "Your choice: "
                raw_input = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        input,
                        prompt_text,
                    ),
                    timeout=float(broadcast_request.timeout),
                )

                raw_input = raw_input.strip()

                # Parse response
                selected_options = []
                other_text = None

                if not raw_input:
                    if question.required:
                        print("⚠️  Required question - selecting first option")
                        selected_options = [question.options[0].id] if question.options else []
                    else:
                        print("⏭️  Skipped")
                elif raw_input.lower().startswith("other:"):
                    other_text = raw_input[6:].strip()
                    print(f"✓ Custom answer: {other_text[:50]}...")
                else:
                    # Parse number selections
                    try:
                        nums = [int(n.strip()) for n in raw_input.split(",") if n.strip()]
                        for num in nums:
                            if 1 <= num <= len(question.options):
                                selected_options.append(question.options[num - 1].id)
                            else:
                                print(f"⚠️ Option {num} out of range, ignoring")

                        if not question.multi_select and len(selected_options) > 1:
                            print("⚠️ Single-select - using first selection only")
                            selected_options = selected_options[:1]

                        if selected_options:
                            labels = [opt.label for opt in question.options if opt.id in selected_options]
                            print(f"✓ Selected: {', '.join(labels)}")
                    except ValueError:
                        # Treat as "other" if not parseable
                        other_text = raw_input
                        print(f"✓ Custom answer: {other_text[:50]}...")

                response = StructuredResponse(
                    question_index=q_idx,
                    selected_options=selected_options,
                    other_text=other_text,
                )
                responses.append(response)

            except TimeoutError:
                print("\n⏱️  Timeout - skipping remaining questions\n")
                return responses if responses else None
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
                return responses if responses else None

        print(f"\n✓ All {len(questions)} questions answered!\n")
        return responses


# Convenience functions for common use cases
async def coordinate_with_terminal_ui(orchestrator, question: str, enable_final_presentation: bool = False, **kwargs) -> str:
    """Quick coordination with terminal UI.

    Args:
        orchestrator: MassGen orchestrator instance
        question: Question for coordination
        enable_final_presentation: Whether to ask winning agent to present final answer
        **kwargs: Additional configuration

    Returns:
        Final coordinated response
    """
    ui = CoordinationUI(
        display_type="terminal",
        enable_final_presentation=enable_final_presentation,
        **kwargs,
    )
    return await ui.coordinate(orchestrator, question)


async def coordinate_with_simple_ui(orchestrator, question: str, enable_final_presentation: bool = False, **kwargs) -> str:
    """Quick coordination with simple UI.

    Args:
        orchestrator: MassGen orchestrator instance
        question: Question for coordination
        **kwargs: Additional configuration

    Returns:
        Final coordinated response
    """
    ui = CoordinationUI(
        display_type="simple",
        enable_final_presentation=enable_final_presentation,
        **kwargs,
    )
    return await ui.coordinate(orchestrator, question)


async def coordinate_with_rich_ui(orchestrator, question: str, enable_final_presentation: bool = False, **kwargs) -> str:
    """Quick coordination with rich terminal UI.

    Args:
        orchestrator: MassGen orchestrator instance
        question: Question for coordination
        enable_final_presentation: Whether to ask winning agent to present final answer
        **kwargs: Additional configuration (theme, refresh_rate, etc.)

    Returns:
        Final coordinated response
    """
    ui = CoordinationUI(
        display_type="rich_terminal",
        enable_final_presentation=enable_final_presentation,
        **kwargs,
    )
    return await ui.coordinate(orchestrator, question)
