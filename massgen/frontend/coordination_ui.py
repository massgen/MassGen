# -*- coding: utf-8 -*-
"""
MassGen Coordination UI

Main interface for coordinating agents with visual display.
"""

import asyncio
from typing import Any, Dict, List, Optional

from .displays.base_display import BaseDisplay
from .displays.rich_terminal_display import RichTerminalDisplay, is_rich_available
from .displays.simple_display import SimpleDisplay
from .displays.terminal_display import TerminalDisplay


class CoordinationUI:
    """Main coordination interface with display capabilities."""

    def __init__(
        self,
        display: Optional[BaseDisplay] = None,
        logger: Optional[Any] = None,
        display_type: str = "terminal",
        enable_final_presentation: bool = False,
        **kwargs,
    ):
        """Initialize coordination UI.

        Args:
            display: Custom display instance (overrides display_type)
            logger: Custom logger instance
            display_type: Type of display ("terminal", "simple", "rich_terminal", "textual_terminal")
            enable_final_presentation: Whether to ask winning agent to present final answer
            **kwargs: Additional configuration passed to display/logger
        """
        self.enable_final_presentation = enable_final_presentation
        self.display = display
        self.logger = logger
        self.display_type = display_type
        self.config = kwargs

        # Will be set during coordination
        self.agent_ids = []
        self.orchestrator = None

        # Flush output configuration (matches rich_terminal_display)
        self._flush_char_delay = 0.03  # 30ms between characters

        # Initialize answer buffer state
        self._answer_buffer = ""
        self._answer_timeout_task = None
        self._final_answer_shown = False

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

    def __post_init__(self):
        """Post-initialization setup."""
        self._flush_word_delay = 0.08  # 80ms after punctuation

        # Initialize answer buffer state
        self._answer_buffer = ""
        self._answer_timeout_task = None
        self._final_answer_shown = False

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

    async def coordinate(self, orchestrator, question: str, agent_ids: Optional[List[str]] = None) -> str:
        """Coordinate agents with visual display.

        Args:
            orchestrator: MassGen orchestrator instance
            question: Question for coordination
            agent_ids: Optional list of agent IDs (auto-detected if not provided)

        Returns:
            Final coordinated response
        """
        # Initialize variables that may be referenced in finally block
        selected_agent = ""
        vote_results = {}
        final_result = ""
        final_answer = ""

        # Reset display to ensure clean state for each coordination
        if self.display is not None:
            self.display.cleanup()
        self.display = None

        self.orchestrator = orchestrator

        # Auto-detect agent IDs if not provided
        if agent_ids is None:
            self.agent_ids = list(orchestrator.agents.keys())
        else:
            self.agent_ids = agent_ids

        # Initialize display if not provided
        if self.display is None:
            if self.display_type == "terminal":
                self.display = TerminalDisplay(self.agent_ids, **self.config)
            elif self.display_type == "simple":
                self.display = SimpleDisplay(self.agent_ids, **self.config)
            elif self.display_type == "rich_terminal":
                if not is_rich_available():
                    print("⚠️  Rich library not available. Falling back to terminal display.")
                    print("   Install with: pip install rich")
                    self.display = TerminalDisplay(self.agent_ids, **self.config)
                else:
                    self.display = RichTerminalDisplay(self.agent_ids, **self.config)
            else:
                raise ValueError(f"Unknown display type: {self.display_type}")

        # Pass orchestrator reference to display for backend info
        self.display.orchestrator = orchestrator

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

        # Initialize variables to avoid reference before assignment error in finally block
        selected_agent = None
        vote_results = {}
        user_quit = False  # Track if user quit

        try:
            # Process coordination stream
            full_response = ""
            final_answer = ""

            async for chunk in orchestrator.chat_simple(question):
                # Check if user requested quit
                if self.display and hasattr(self.display, "_user_quit_requested") and self.display._user_quit_requested:
                    # User pressed 'q' - exit gracefully
                    user_quit = True
                    raise SystemExit(0)

                content = getattr(chunk, "content", "") or ""
                source = getattr(chunk, "source", None)
                chunk_type = getattr(chunk, "type", "")

                # Handle agent status updates
                if chunk_type == "agent_status":
                    status = getattr(chunk, "status", None)
                    if source and status:
                        self.display.update_agent_status(source, status)
                    continue

                # Filter out debug chunks from display
                elif chunk_type == "debug":
                    # Log debug info but don't display it
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Filter out mcp_status chunks - display via agent panel instead of console
                elif chunk_type == "mcp_status":
                    # Let the display handle MCP status via agent panel
                    if source and source in self.agent_ids:
                        self.display.update_agent_content(source, content, "tool")
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

                # Handle restart banner
                elif chunk_type == "restart_banner":
                    # Extract restart info from orchestrator state
                    reason = getattr(orchestrator, "restart_reason", "Answer needs improvement")
                    instructions = getattr(orchestrator, "restart_instructions", "Please address the issues identified")
                    # Next attempt number (current is 0-indexed, so current_attempt=0 means attempt 1 just finished, attempt 2 is next)
                    attempt = getattr(orchestrator, "current_attempt", 0) + 2
                    max_attempts = getattr(orchestrator, "max_attempts", 3)

                    self.display.show_restart_banner(reason, instructions, attempt, max_attempts)
                    continue

                # Handle restart required signal (internal - don't display)
                elif chunk_type == "restart_required":
                    # Signal that orchestration will restart - UI will be reinitialized
                    continue

                # Reset reasoning prefix state when final presentation starts
                if chunk_type == "status" and "presenting final answer" in content:
                    # Clear all summary active flags for final presentation
                    for attr_name in list(vars(self).keys()):
                        if attr_name.startswith("_summary_active_"):
                            delattr(self, attr_name)

                # Handle post-evaluation content streaming
                if source and content and chunk_type == "content":
                    # Check if we're in post-evaluation
                    if hasattr(self, "_in_post_evaluation") and self._in_post_evaluation:
                        if self.display and hasattr(self.display, "show_post_evaluation_content"):
                            self.display.show_post_evaluation_content(content, source)

                # Detect post-evaluation start
                if chunk_type == "status" and "Post-evaluation" in content:
                    self._in_post_evaluation = True

                if content:
                    full_response += content

                    # Log chunk
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk.type)

                    # Process content by source
                    await self._process_content(source, content)

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

            # Use orchestrator's clean answer or fall back to full response
            final_result = orchestrator_final_answer if orchestrator_final_answer else full_response

            # Finalize session
            if self.logger:
                session_info = self.logger.finalize_session(
                    final_result if "final_result" in locals() else (final_answer if "final_answer" in locals() else ""),
                    success=True,
                )
                print(f"💾 Session log: {session_info['filename']}")
                print(f"⏱️  Duration: {session_info['duration']:.1f}s | Chunks: {session_info['total_chunks']} | Events: {session_info['orchestrator_events']}")

            return final_result

        except SystemExit:
            # User pressed 'q' - cleanup and exit gracefully
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
                except (asyncio.TimeoutError, asyncio.CancelledError):
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

            # Small delay to ensure display updates are processed
            try:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass  # Silently handle cancellation

            # Only cleanup (which shows inspection menu) if coordination is truly finished
            # Check workflow_phase to see if we're in "presenting" state (finished) vs still coordinating (restarting)
            is_finished = hasattr(orchestrator, "workflow_phase") and orchestrator.workflow_phase == "presenting"
            if self.display and is_finished:
                self.display.cleanup()

            # Don't print - display already showed this info
            # if selected_agent:
            #     print(f"✅ Selected by: {selected_agent}")
            #     if vote_results.get("vote_counts"):
            #         vote_summary = ", ".join([f"{agent}: {count}" for agent, count in vote_results["vote_counts"].items()])
            #         print(f"🗳️ Vote results: {vote_summary}")
            # print()

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
        messages: List[Dict[str, Any]],
        agent_ids: Optional[List[str]] = None,
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
        # Initialize variables that may be referenced in finally block
        selected_agent = ""
        vote_results = {}
        final_result = ""
        final_answer = ""

        # Reset display to ensure clean state for each coordination
        if self.display is not None:
            self.display.cleanup()
        self.display = None

        self.orchestrator = orchestrator

        # Auto-detect agent IDs if not provided
        if agent_ids is None:
            self.agent_ids = list(orchestrator.agents.keys())
        else:
            self.agent_ids = agent_ids

        # Initialize display if not provided
        if self.display is None:
            if self.display_type == "terminal":
                self.display = TerminalDisplay(self.agent_ids, **self.config)
            elif self.display_type == "simple":
                self.display = SimpleDisplay(self.agent_ids, **self.config)
            elif self.display_type == "rich_terminal":
                if not is_rich_available():
                    print("⚠️  Rich library not available. Falling back to terminal display.")
                    print("   Install with: pip install rich")
                    self.display = TerminalDisplay(self.agent_ids, **self.config)
                else:
                    self.display = RichTerminalDisplay(self.agent_ids, **self.config)
            else:
                raise ValueError(f"Unknown display type: {self.display_type}")

        # Pass orchestrator reference to display for backend info
        self.display.orchestrator = orchestrator

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
                # Check if user requested quit
                if self.display and hasattr(self.display, "_user_quit_requested") and self.display._user_quit_requested:
                    # User pressed 'q' - exit gracefully
                    user_quit = True
                    raise SystemExit(0)

                content = getattr(chunk, "content", "") or ""
                source = getattr(chunk, "source", None)
                chunk_type = getattr(chunk, "type", "")

                # Handle agent status updates
                if chunk_type == "agent_status":
                    status = getattr(chunk, "status", None)
                    if source and status:
                        self.display.update_agent_status(source, status)
                    continue

                # Filter out debug chunks from display
                elif chunk_type == "debug":
                    # Log debug info but don't display it
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk_type)
                    continue

                # Filter out mcp_status chunks - display via agent panel instead of console
                elif chunk_type == "mcp_status":
                    # Let the display handle MCP status via agent panel
                    if source and source in self.agent_ids:
                        self.display.update_agent_content(source, content, "tool")
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

                # Handle restart banner
                elif chunk_type == "restart_banner":
                    # Extract restart info from orchestrator state
                    reason = getattr(orchestrator, "restart_reason", "Answer needs improvement")
                    instructions = getattr(orchestrator, "restart_instructions", "Please address the issues identified")
                    # Next attempt number (current is 0-indexed, so current_attempt=0 means attempt 1 just finished, attempt 2 is next)
                    attempt = getattr(orchestrator, "current_attempt", 0) + 2
                    max_attempts = getattr(orchestrator, "max_attempts", 3)

                    self.display.show_restart_banner(reason, instructions, attempt, max_attempts)
                    continue

                # Handle restart required signal (internal - don't display)
                elif chunk_type == "restart_required":
                    # Signal that orchestration will restart - UI will be reinitialized
                    continue

                # Reset reasoning prefix state when final presentation starts
                if chunk_type == "status" and "presenting final answer" in content:
                    # Clear all summary active flags for final presentation
                    for attr_name in list(vars(self).keys()):
                        if attr_name.startswith("_summary_active_"):
                            delattr(self, attr_name)

                # Handle post-evaluation content streaming
                if source and content and chunk_type == "content":
                    # Check if we're in post-evaluation by looking for the status message
                    if hasattr(self, "_in_post_evaluation") and self._in_post_evaluation:
                        if self.display and hasattr(self.display, "show_post_evaluation_content"):
                            self.display.show_post_evaluation_content(content, source)

                # Detect post-evaluation start
                if chunk_type == "status" and "Post-evaluation" in content:
                    self._in_post_evaluation = True

                if content:
                    full_response += content

                    # Log chunk
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk.type)

                    # Process content by source
                    await self._process_content(source, content)

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

            # Use orchestrator's clean answer or fall back to full response
            final_result = orchestrator_final_answer if orchestrator_final_answer else full_response

            # Finalize session
            if self.logger:
                session_info = self.logger.finalize_session(
                    final_result if "final_result" in locals() else (final_answer if "final_answer" in locals() else ""),
                    success=True,
                )
                print(f"💾 Session log: {session_info['filename']}")
                print(f"⏱️  Duration: {session_info['duration']:.1f}s | Chunks: {session_info['total_chunks']} | Events: {session_info['orchestrator_events']}")

            return final_result

        except SystemExit:
            # User pressed 'q' - cleanup and exit gracefully
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
                except (asyncio.TimeoutError, asyncio.CancelledError):
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

            # Small delay to ensure display updates are processed
            try:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass  # Silently handle cancellation

            # Only cleanup (which shows inspection menu) if coordination is truly finished
            is_finished = hasattr(orchestrator, "workflow_phase") and orchestrator.workflow_phase == "presenting"
            if self.display and is_finished:
                self.display.cleanup()

    def _display_vote_results(self, vote_results: Dict[str, Any]):
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

    async def _process_content(self, source: Optional[str], content: str):
        """Process content from coordination stream."""
        # Handle agent content
        if source in self.agent_ids:
            await self._process_agent_content(source, content)

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

    async def _process_agent_content(self, agent_id: str, content: str):
        """Process content from a specific agent."""
        # Update agent status - if agent is streaming content, they're working
        # But don't override "completed" status
        current_status = self.display.get_agent_status(agent_id)
        if current_status not in ["working", "completed"]:
            self.display.update_agent_status(agent_id, "working")

        # Determine content type and process
        if "🔧" in content or "🔄 Vote invalid" in content:
            # Tool usage or status messages
            content_type = "tool" if "🔧" in content else "status"
            self.display.update_agent_content(agent_id, content, content_type)

            # Update status on completion
            if "new_answer" in content or "vote" in content:
                self.display.update_agent_status(agent_id, "completed")

            # Log to detailed logger
            if self.logger:
                self.logger.log_agent_content(agent_id, content, content_type)

        else:
            # Thinking content
            self.display.update_agent_content(agent_id, content, "thinking")
            if self.logger:
                self.logger.log_agent_content(agent_id, content, "thinking")

    async def _flush_final_answer(self):
        """Flush the buffered final answer after a timeout to prevent duplicate calls."""
        if self._final_answer_shown or not self._answer_buffer.strip():
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
        selected_agent = status.get("selected_agent", "Unknown")
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
                selected_agent = status.get("selected_agent", "Unknown")
                vote_results = status.get("vote_results", {})
                vote_counts = vote_results.get("vote_counts", {})
                is_tie = vote_results.get("is_tie", False)

                # Only create final event for first chunk to avoid spam
                if self._answer_buffer == clean_content:  # First chunk
                    # Check if orchestrator timed out
                    orchestrator_timeout = getattr(self.orchestrator, "is_orchestrator_timeout", False)

                    if selected_agent == "Unknown" or selected_agent is None:
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
