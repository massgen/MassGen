"""Post-evaluation streaming + restart bookkeeping, extracted from Orchestrator.

Owns the two public-ish methods ``post_evaluate_answer`` (async generator) and
``handle_restart`` (state reset). Both touch shared Orchestrator state, so
every mutation goes through ``self._orchestrator.<field>`` and never via a
local copy. This is critical because ``handle_restart`` REBUILDS
``coordination_tracker`` and RESETS the entire ``agent_states`` dict — any
other collaborator holding a back-ref to the Orchestrator must observe those
new instances.

Patchable symbols (``get_event_emitter``, ``get_post_evaluation_tools``,
``CoordinationTracker``, ``SystemMessageBuilder``, ``get_log_session_dir``,
``log_stream_chunk``, ``log_orchestrator_activity``, ``logger``) are looked
up via the orchestrator module so test ``patch("massgen.orchestrator.<sym>")``
hooks keep working.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from massgen.backend.base import StreamChunk
from massgen.utils import CoordinationStage

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class PostEvaluationRunner:
    """Runs the post-evaluation streaming loop and the restart state reset."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def post_evaluate_answer(
        self,
        selected_agent_id: str,
        final_answer: str,
    ) -> AsyncGenerator[StreamChunk]:
        """Post-evaluation phase where winning agent evaluates its own answer."""
        # Import via orchestrator module so test patches at
        # ``massgen.orchestrator.<symbol>`` take effect.
        from massgen import orchestrator as _orch_mod

        orch = self._orchestrator

        if selected_agent_id not in orch.agents:
            _orch_mod.log_stream_chunk(
                "orchestrator",
                "error",
                f"Selected agent {selected_agent_id} not found for post-evaluation",
            )
            yield StreamChunk(
                type="error",
                error=f"Selected agent {selected_agent_id} not found",
            )
            return

        agent = orch.agents[selected_agent_id]

        # Use debug override on first attempt if configured
        eval_answer = final_answer
        if orch.config.debug_final_answer and orch.current_attempt == 0:
            eval_answer = orch.config.debug_final_answer
            _orch_mod.log_stream_chunk(
                "orchestrator",
                "debug",
                f"Using debug override for post-evaluation: {orch.config.debug_final_answer}",
            )
            yield StreamChunk(
                type="debug",
                content=f"[DEBUG MODE] Overriding answer for evaluation: {orch.config.debug_final_answer}",
                source="orchestrator",
            )

        # Build evaluation message
        evaluation_content = f"""{orch.message_templates.format_original_message(orch.current_task or "Task")}

FINAL ANSWER TO EVALUATE:
{eval_answer}

Review this answer carefully and determine if it fully addresses the original task. Use your available tools to verify claims and check files as needed.
Then call either submit(confirmed=True) if the answer is satisfactory, or restart_orchestration(reason, instructions) if improvements are needed."""

        # Get all answers for context
        all_answers = {aid: s.answer for aid, s in orch.agent_states.items() if s.answer}

        # Build post-evaluation system message using section architecture
        base_system_message = orch._get_system_message_builder().build_post_evaluation_message(
            agent=agent,
            all_answers=all_answers,
            previous_turns=orch._previous_turns,
        )

        # Create evaluation messages
        evaluation_messages = [
            {"role": "system", "content": base_system_message},
            {"role": "user", "content": evaluation_content},
        ]

        # Get post-evaluation tools
        api_format = "chat_completions"  # Default format
        if hasattr(agent.backend, "api_format"):
            api_format = agent.backend.api_format
        post_eval_tools = _orch_mod.get_post_evaluation_tools(api_format=api_format)

        _orch_mod.log_stream_chunk(
            "orchestrator",
            "status",
            "🔍 Post-evaluation: Reviewing final answer\n",
        )
        yield StreamChunk(
            type="status",
            content="🔍 Post-evaluation: Reviewing final answer\n",
            source="orchestrator",
        )

        # Emit post_evaluation start event for unified pipeline
        _pe_emitter = _orch_mod.get_event_emitter()
        if _pe_emitter:
            _pe_emitter.emit_post_evaluation(
                phase="start",
                content="Post-evaluation: Reviewing final answer",
                agent_id=selected_agent_id,
            )

        # Start round token tracking for post-evaluation
        post_eval_round = orch.coordination_tracker.get_agent_round(selected_agent_id) + 1
        if hasattr(agent.backend, "start_round_tracking"):
            agent.backend.start_round_tracking(
                round_number=post_eval_round,
                round_type="post_evaluation",
                agent_id=selected_agent_id,
            )

        # Stream evaluation with tools (with timeout protection)
        evaluation_complete = False
        tool_call_detected = False
        accumulated_content = ""  # Buffer to detect inline JSON across chunks

        try:
            timeout_seconds = orch.config.timeout_config.orchestrator_timeout_seconds
            async with asyncio.timeout(timeout_seconds):
                async for chunk in agent.chat(
                    messages=evaluation_messages,
                    tools=post_eval_tools,
                    reset_chat=True,  # Reset conversation history for clean evaluation
                    current_stage=CoordinationStage.POST_EVALUATION,
                    orchestrator_turn=orch._current_turn,
                    previous_winners=orch._winning_agents_history.copy(),
                ):
                    chunk_type = orch._get_chunk_type_value(chunk)

                    # Skip content/reasoning after evaluation decision (submit/restart)
                    # to prevent stray text appearing after answer_locked
                    if evaluation_complete and chunk_type in (
                        "content",
                        "reasoning",
                        "reasoning_done",
                        "reasoning_summary",
                        "reasoning_summary_done",
                    ):
                        continue

                    if chunk_type == "content" and chunk.content:
                        _orch_mod.log_stream_chunk(
                            "orchestrator",
                            "content",
                            chunk.content,
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type="content",
                            content=chunk.content,
                            source=selected_agent_id,
                        )
                        # Emit post_evaluation content for unified pipeline
                        if _pe_emitter:
                            _pe_emitter.emit_post_evaluation(
                                phase="content",
                                content=chunk.content,
                                agent_id=selected_agent_id,
                            )

                        # Accumulate content for JSON parsing across chunks
                        accumulated_content += chunk.content

                        # Fallback: parse inline JSON tool calls from accumulated content
                        # Some backends output submit/restart as JSON text instead of tool_calls
                        if not evaluation_complete and not tool_call_detected:
                            # Find JSON objects in the content (handle nested braces)
                            json_matches = re.findall(
                                r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"action_type"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
                                accumulated_content,
                                re.DOTALL,
                            )
                            for json_str in json_matches:
                                try:
                                    data = json.loads(json_str)
                                    action_type = data.get("action_type")

                                    if action_type == "submit":
                                        tool_call_detected = True
                                        _orch_mod.log_stream_chunk(
                                            "orchestrator",
                                            "status",
                                            "✅ Evaluation complete - answer approved\n",
                                        )
                                        yield StreamChunk(
                                            type="status",
                                            content="✅ Evaluation complete - answer approved\n",
                                            source="orchestrator",
                                        )
                                        evaluation_complete = True
                                        break
                                    elif action_type == "restart_orchestration":
                                        tool_call_detected = True
                                        restart_data = data.get("restart_data", {})
                                        orch.restart_reason = restart_data.get(
                                            "reason",
                                            data.get("reason", "Answer needs improvement"),
                                        )
                                        orch.restart_instructions = restart_data.get(
                                            "instructions",
                                            data.get("instructions", ""),
                                        )
                                        orch.restart_pending = True

                                        _orch_mod.log_stream_chunk(
                                            "orchestrator",
                                            "status",
                                            "🔄 Restart requested\n",
                                        )
                                        yield StreamChunk(
                                            type="status",
                                            content="🔄 Restart requested\n",
                                            source="orchestrator",
                                        )
                                        evaluation_complete = True
                                        break
                                except json.JSONDecodeError:
                                    # Not valid JSON yet, keep accumulating
                                    pass
                    elif chunk_type in [
                        "reasoning",
                        "reasoning_done",
                        "reasoning_summary",
                        "reasoning_summary_done",
                    ]:
                        reasoning_chunk = StreamChunk(
                            type=chunk_type,
                            content=chunk.content,
                            source=selected_agent_id,
                            reasoning_delta=getattr(chunk, "reasoning_delta", None),
                            reasoning_text=getattr(chunk, "reasoning_text", None),
                            reasoning_summary_delta=getattr(
                                chunk,
                                "reasoning_summary_delta",
                                None,
                            ),
                            reasoning_summary_text=getattr(
                                chunk,
                                "reasoning_summary_text",
                                None,
                            ),
                            item_id=getattr(chunk, "item_id", None),
                            content_index=getattr(chunk, "content_index", None),
                            summary_index=getattr(chunk, "summary_index", None),
                        )
                        _orch_mod.log_stream_chunk(
                            "orchestrator",
                            chunk.type,
                            chunk.content,
                            selected_agent_id,
                        )
                        yield reasoning_chunk
                        # Emit thinking events for the unified event pipeline
                        if _pe_emitter and chunk.content:
                            _pe_emitter.emit_thinking(
                                content=chunk.content,
                                agent_id=selected_agent_id,
                            )
                        if _pe_emitter and chunk_type in ("reasoning_done", "reasoning_summary_done"):
                            from massgen.events import EventType as _EvType

                            _pe_emitter.emit_raw(
                                _EvType.THINKING,
                                content="",
                                done=True,
                                agent_id=selected_agent_id,
                            )
                    elif chunk_type == "tool_calls":
                        # Post-evaluation tool call detected - only set flag if valid tool found
                        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                            for tool_call in chunk.tool_calls:
                                # Use backend's tool extraction (same as regular coordination)
                                tool_name = agent.backend.extract_tool_name(tool_call)
                                tool_args = agent.backend.extract_tool_arguments(
                                    tool_call,
                                )

                                # Only set tool_call_detected if we got a valid tool name
                                if tool_name:
                                    tool_call_detected = True

                                if tool_name == "submit":
                                    _orch_mod.log_stream_chunk(
                                        "orchestrator",
                                        "status",
                                        "✅ Evaluation complete - answer approved\n",
                                    )
                                    yield StreamChunk(
                                        type="status",
                                        content="✅ Evaluation complete - answer approved\n",
                                        source="orchestrator",
                                    )
                                    evaluation_complete = True
                                elif tool_name == "restart_orchestration":
                                    # Parse restart parameters from extracted args
                                    orch.restart_reason = tool_args.get(
                                        "reason",
                                        "No reason provided",
                                    )
                                    orch.restart_instructions = tool_args.get(
                                        "instructions",
                                        "No instructions provided",
                                    )
                                    orch.restart_pending = True

                                    # Save the current winning answer for next attempt's context
                                    if orch._selected_agent and orch._selected_agent in orch.agent_states:
                                        orch.previous_attempt_answer = orch.agent_states[orch._selected_agent].answer
                                        _orch_mod.logger.info(
                                            f"Saved previous attempt answer from {orch._selected_agent} for restart context",
                                        )

                                    _orch_mod.log_stream_chunk(
                                        "orchestrator",
                                        "status",
                                        "🔄 Restart requested\n",
                                    )
                                    yield StreamChunk(
                                        type="status",
                                        content="🔄 Restart requested\n",
                                        source="orchestrator",
                                    )
                                    evaluation_complete = True
                    elif chunk_type == "done":
                        _orch_mod.log_stream_chunk(
                            "orchestrator",
                            "done",
                            None,
                            selected_agent_id,
                        )
                        yield StreamChunk(type="done", source=selected_agent_id)
                    elif chunk_type == "error":
                        _orch_mod.log_stream_chunk(
                            "orchestrator",
                            "error",
                            chunk.error,
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type="error",
                            error=chunk.error,
                            source=selected_agent_id,
                        )
                    else:
                        # Pass through other chunk types
                        _orch_mod.log_stream_chunk(
                            "orchestrator",
                            chunk_type,
                            getattr(chunk, "content", ""),
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{
                                k: v
                                for k, v in chunk.__dict__.items()
                                if k
                                not in [
                                    "type",
                                    "content",
                                    "source",
                                    "timestamp",
                                    "sequence_number",
                                ]
                            },
                        )
        except TimeoutError:
            _orch_mod.log_stream_chunk(
                "orchestrator",
                "status",
                "⏱️ Post-evaluation timed out - auto-submitting answer\n",
            )
            yield StreamChunk(
                type="status",
                content="⏱️ Post-evaluation timed out - auto-submitting answer\n",
                source="orchestrator",
            )
            evaluation_complete = True
            # Don't set restart_pending - let it default to False (auto-submit)
        finally:
            # Note: end_round_tracking for post_evaluation is called from _present_final_answer
            # after the async for loop completes, to ensure reliable timing before save_coordination_logs

            # Emit post_evaluation end event for unified pipeline
            if _pe_emitter:
                winner = selected_agent_id if not orch.restart_pending else None
                _pe_emitter.emit_post_evaluation(
                    phase="end",
                    winner=winner,
                    agent_id=selected_agent_id,
                )

            # If evaluation didn't complete (no submit/restart called), auto-submit
            if not evaluation_complete:
                _orch_mod.log_stream_chunk(
                    "orchestrator",
                    "status",
                    "✅ Evaluation complete - answer approved\n",
                )
                yield StreamChunk(
                    type="status",
                    content="✅ Evaluation complete - answer approved\n",
                    source="orchestrator",
                )

    def handle_restart(self) -> None:
        """Reset orchestration state for restart attempt.

        Clears agent states and coordination messages while preserving
        restart reason and instructions for the next attempt. All mutations
        go through the orchestrator back-ref so already-extracted
        collaborators see the new coordination_tracker / agent_states.
        """
        from massgen import orchestrator as _orch_mod

        orch = self._orchestrator

        _orch_mod.log_orchestrator_activity(
            "handle_restart",
            f"Resetting state for restart attempt {orch.current_attempt + 1}",
        )

        # Reset agent states (in-place mutation of the live dict)
        AgentState = _orch_mod.AgentState
        for agent_id in orch.agent_states:
            orch.agent_states[agent_id] = AgentState()

        # Clear coordination messages
        orch._coordination_messages = []
        orch._selected_agent = None
        orch._final_presentation_content = None

        # Reset coordination tracker for new attempt (MAS-199: includes log_path)
        orch.coordination_tracker = _orch_mod.CoordinationTracker()
        log_dir = _orch_mod.get_log_session_dir()
        log_path = str(log_dir) if log_dir else None
        orch.coordination_tracker.initialize_session(
            list(orch.agents.keys()),
            log_path=log_path,
        )

        # Reset MCP initialization flag to force tool re-setup on next agent.chat()
        for agent_key, agent in orch.agents.items():
            if hasattr(agent.backend, "_mcp_initialized"):
                agent.backend._mcp_initialized = False
                _orch_mod.logger.info(
                    f"[Orchestrator] Reset MCP initialized flag for agent {agent_key}",
                )

        # Reset workflow phase to idle so next coordinate() call starts fresh
        orch.workflow_phase = "idle"

        # Increment attempt counter
        orch.current_attempt += 1

        _orch_mod.log_orchestrator_activity(
            "handle_restart",
            f"State reset complete - starting attempt {orch.current_attempt + 1}",
        )
