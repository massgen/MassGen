"""Runtime user-input delivery, extracted from Orchestrator.

Owns the runtime ``HumanInputHook`` and ``RuntimeInboxPoller`` lifecycle,
plus the helpers that splice runtime instructions into agent messages and
that drive the manual "Answer Now" wrap-up signaling. All shared state
(``_human_input_hook``, ``_runtime_inbox_poller``) is mutated via the
orchestrator back-ref so other collaborators continue to see a single
source of truth.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from massgen.logger_config import logger
from massgen.mcp_tools.hooks import HumanInputHook
from massgen.structured_logging import (  # noqa: F401 - parity with orchestrator
    get_tracer as _unused_tracer,
)

# Avoid importing get_event_emitter at module import; tests patch the module-level
# symbol on massgen.orchestrator. We import lazily inside methods.

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class RuntimeInputDelivery:
    """Coordinates runtime-input hook + inbox poller + Answer Now signaling."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Runtime user-instructions context block helpers
    # ------------------------------------------------------------------
    def build_runtime_user_instructions_context(self, agent_id: str) -> str | None:
        orch = self._orchestrator
        if not orch._human_input_hook:
            return None

        getter = getattr(orch._human_input_hook, "get_delivered_messages_for_agent", None)
        if not callable(getter):
            return None

        delivered_entries = getter(agent_id) or []
        if not delivered_entries:
            return None

        lines = [
            "<RUNTIME USER INSTRUCTIONS>",
            "The user provided these runtime instructions earlier in this turn.",
            "Continue honoring them unless newer instructions supersede them:",
        ]

        entry_index = 1
        for entry in delivered_entries:
            content = str((entry or {}).get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{entry_index}. {content}")
            entry_index += 1

        if entry_index == 1:
            return None

        lines.append("<END OF RUNTIME USER INSTRUCTIONS>")
        return "\n".join(lines)

    @staticmethod
    def insert_runtime_user_instructions_after_original_message(
        user_message: str,
        runtime_instructions_block: str,
    ) -> str:
        return RuntimeInputDelivery.insert_runtime_context_blocks_after_original_message(
            user_message,
            [runtime_instructions_block],
        )

    @staticmethod
    def insert_runtime_context_blocks_after_original_message(
        user_message: str,
        context_blocks: Sequence[str | None],
    ) -> str:
        normalized_blocks = [str(block or "").strip() for block in context_blocks if str(block or "").strip()]
        if not normalized_blocks:
            return user_message

        merged_block = "\n\n".join(normalized_blocks)
        current_user_message = user_message or ""
        if not current_user_message:
            return merged_block

        end_paraphrased = "<END OF PARAPHRASED MESSAGE>"
        end_original = "<END OF ORIGINAL MESSAGE>"

        insertion_anchor = None
        if end_paraphrased in current_user_message:
            insertion_anchor = end_paraphrased
        elif end_original in current_user_message:
            insertion_anchor = end_original

        if not insertion_anchor:
            return merged_block + "\n\n" + current_user_message

        anchor_start = current_user_message.find(insertion_anchor)
        if anchor_start < 0:
            return merged_block + "\n\n" + current_user_message

        anchor_end = anchor_start + len(insertion_anchor)
        before = current_user_message[:anchor_end]
        after = current_user_message[anchor_end:].lstrip("\n")

        if after:
            return f"{before}\n\n{merged_block}\n\n{after}"
        return f"{before}\n\n{merged_block}"

    # ------------------------------------------------------------------
    # Runtime hook + inbox lifecycle
    # ------------------------------------------------------------------
    def ensure_runtime_human_input_hook_initialized(self) -> None:
        orch = self._orchestrator
        if orch._human_input_hook is None:
            orch._human_input_hook = HumanInputHook()
            self.configure_human_input_hook_callbacks()
            self.share_human_input_hook_with_display()
            return

        self.configure_human_input_hook_callbacks()

    def ensure_runtime_inbox_poller_initialized(self) -> None:
        orch = self._orchestrator
        if orch._runtime_inbox_poller is not None:
            return

        workspace_path: Path | None = None
        backend_workspace_path: Path | None = None

        for agent in orch.agents.values():
            backend = getattr(agent, "backend", None)
            filesystem_manager = getattr(backend, "filesystem_manager", None) if backend else None
            if not filesystem_manager:
                continue

            get_workspace = getattr(filesystem_manager, "get_current_workspace", None)
            if callable(get_workspace):
                resolved = get_workspace()
                if resolved:
                    backend_workspace_path = Path(resolved)
                    break

            cwd = getattr(filesystem_manager, "cwd", None)
            if cwd:
                backend_workspace_path = Path(cwd)
                break

        if orch._agent_temporary_workspace:
            temp_workspace = Path(orch._agent_temporary_workspace)
            if temp_workspace.name == "temp" and temp_workspace.parent:
                workspace_path = temp_workspace.parent
            elif temp_workspace.name == "temp_workspaces":
                workspace_path = None
            elif temp_workspace.parent.name == "temp_workspaces":
                workspace_path = temp_workspace

        if workspace_path is None:
            workspace_path = backend_workspace_path

        if workspace_path is None:
            return

        from massgen.mcp_tools.hooks import RuntimeInboxPoller

        inbox_dir = workspace_path / ".massgen" / "runtime_inbox"
        orch._runtime_inbox_poller = RuntimeInboxPoller(inbox_dir=inbox_dir)
        logger.info(
            f"[Orchestrator] Initialized runtime inbox poller: {inbox_dir}",
        )

    def poll_runtime_inbox(self) -> None:
        orch = self._orchestrator
        if not orch._runtime_inbox_poller:
            return

        messages = orch._runtime_inbox_poller.poll()
        if not messages:
            return

        self.ensure_runtime_human_input_hook_initialized()
        # Import lazily so tests that patch massgen.orchestrator.get_event_emitter
        # still observe the patched symbol.
        from massgen.orchestrator import get_event_emitter

        _inj_emitter = get_event_emitter()
        for msg in messages:
            content = msg["content"] if isinstance(msg, dict) else msg
            target_agents = msg.get("target_agents") if isinstance(msg, dict) else None
            source = msg.get("source") if isinstance(msg, dict) else None
            source_label = str(source or "parent")
            logger.info(
                f"[Orchestrator] Injecting runtime inbox message: '{content[:80]}' " f"(target={target_agents}, source={source_label})",
            )
            if orch._human_input_hook:
                orch._human_input_hook.set_pending_input(
                    content,
                    target_agents=target_agents,
                    source=source_label,
                )
            if _inj_emitter:
                if isinstance(target_agents, list):
                    recipient_agent_ids = [aid for aid in target_agents if isinstance(aid, str) and aid.strip()]
                else:
                    recipient_agent_ids = list(orch.agents.keys())
                for recipient_agent_id in dict.fromkeys(recipient_agent_ids):
                    _inj_emitter.emit_injection_received(
                        agent_id=recipient_agent_id,
                        source_agents=[source_label],
                        injection_type="runtime_inbox_input",
                    )

    def configure_human_input_hook_callbacks(self) -> None:
        orch = self._orchestrator
        if not orch._human_input_hook:
            return

        def _on_human_input_queued(
            _content: str,
            target_agents: list[str] | None = None,
            _message_id: int | None = None,
        ) -> None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return

            if target_agents:
                candidate_agent_ids = [aid for aid in target_agents if isinstance(aid, str) and aid in orch.agents]
            else:
                candidate_agent_ids = list(orch.agents.keys())

            for candidate_agent_id in candidate_agent_ids:
                loop.create_task(
                    orch._maybe_interrupt_background_wait_for_agent(
                        candidate_agent_id,
                        trigger="queued_human_input",
                    ),
                )

        orch._human_input_hook.set_queue_callback(_on_human_input_queued)
        orch._human_input_hook.set_pre_execute_callback(orch._poll_runtime_inbox)

    async def maybe_interrupt_background_wait_for_agent(
        self,
        agent_id: str,
        trigger: str = "runtime_injection_available",
    ) -> bool:
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if agent is None:
            return False

        backend = getattr(agent, "backend", None)
        if backend is None:
            return False

        is_wait_active = getattr(backend, "is_background_wait_active", None)
        notify_interrupt = getattr(backend, "notify_background_wait_interrupt", None)
        if not callable(is_wait_active) or not callable(notify_interrupt):
            return False

        try:
            if not bool(is_wait_active()):
                return False
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[Orchestrator] Failed checking background wait state for %s: %s",
                agent_id,
                e,
            )
            return False

        runtime_sections = await orch._collect_no_hook_runtime_fallback_sections(agent_id)
        if not runtime_sections:
            return False

        payload = {
            "interrupt_reason": "runtime_injection_available",
            "injected_content": "\n".join(runtime_sections),
            "trigger": trigger,
            "agent_id": agent_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            signaled = bool(notify_interrupt(payload))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[Orchestrator] Failed sending background wait interrupt to %s: %s",
                agent_id,
                e,
                exc_info=True,
            )
            return False

        if signaled:
            logger.info(
                "[Orchestrator] Background wait interrupted for %s via %s",
                agent_id,
                trigger,
            )
        return signaled

    def share_human_input_hook_with_display(self) -> None:
        orch = self._orchestrator
        if not orch._human_input_hook:
            return

        display = None
        if hasattr(orch, "coordination_ui") and orch.coordination_ui:
            display = getattr(orch.coordination_ui, "display", None)

        if not display:
            logger.debug("[Orchestrator] No display available for human input hook sharing")
            return

        if hasattr(display, "set_human_input_hook"):
            display.set_human_input_hook(orch._human_input_hook)
            logger.info("[Orchestrator] Shared human input hook with TUI display")
        else:
            logger.debug("[Orchestrator] Display does not support human input hook")

    # ------------------------------------------------------------------
    # Answer Now wrap-up signaling
    # ------------------------------------------------------------------
    def request_answer_now(self) -> dict[str, list[str]]:
        orch = self._orchestrator
        active_agents: list[str] = []
        if hasattr(orch, "_active_streams") and orch._active_streams:
            active_agents.extend(orch._active_streams.keys())
        if hasattr(orch, "_active_tasks") and orch._active_tasks:
            for agent_id in orch._active_tasks.keys():
                if agent_id not in active_agents:
                    active_agents.append(agent_id)

        if not active_agents:
            for agent_id in orch.agents.keys():
                state = orch.agent_states.get(agent_id)
                if state is None or state.is_killed or state.has_voted:
                    continue
                if state.round_start_time is None or not state.round_timeout_hooks:
                    continue
                active_agents.append(agent_id)

        requested_agents: list[str] = []
        already_requested_agents: list[str] = []
        skipped_agents: list[str] = []

        display = None
        if hasattr(orch, "coordination_ui") and orch.coordination_ui:
            display = getattr(orch.coordination_ui, "display", None)

        for agent_id in active_agents:
            state = orch.agent_states.get(agent_id)
            if state is None or state.is_killed:
                skipped_agents.append(agent_id)
                continue

            hooks = state.round_timeout_hooks
            if not hooks:
                skipped_agents.append(agent_id)
                continue

            post_hook, _ = hooks
            request_wrap_up = getattr(post_hook, "request_wrap_up", None)
            if not callable(request_wrap_up):
                skipped_agents.append(agent_id)
                continue

            if request_wrap_up():
                requested_agents.append(agent_id)
                self.prime_answer_now_hook_payload(agent_id)
                timeout_state = orch.get_agent_timeout_state(agent_id)
                if display and hasattr(display, "update_timeout_status") and timeout_state:
                    display.update_timeout_status(agent_id, timeout_state)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None:
                    loop.create_task(
                        orch._maybe_interrupt_background_wait_for_agent(
                            agent_id,
                            trigger="answer_now_requested",
                        ),
                    )
            else:
                already_requested_agents.append(agent_id)

        logger.info(
            f"[Orchestrator] Answer Now requested: requested={requested_agents} " f"already_requested={already_requested_agents} skipped={skipped_agents}",
        )
        return {
            "requested_agents": requested_agents,
            "already_requested_agents": already_requested_agents,
            "skipped_agents": skipped_agents,
        }

    def consume_pending_answer_now_injection(self, agent_id: str) -> str | None:
        orch = self._orchestrator
        state = orch.agent_states.get(agent_id)
        if state is None or not state.round_timeout_hooks:
            return None

        post_hook, _ = state.round_timeout_hooks
        consume_pending = getattr(post_hook, "consume_pending_wrap_up_injection", None)
        if not callable(consume_pending):
            return None

        try:
            content = consume_pending()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[Orchestrator] Failed consuming Answer Now injection for {agent_id}: {e}",
                exc_info=True,
            )
            return None

        if not content:
            return None
        return str(content)

    def prime_answer_now_hook_payload(self, agent_id: str) -> bool:
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        backend = getattr(agent, "backend", None) if agent is not None else None
        write_hook = getattr(backend, "write_post_tool_use_hook", None)
        if not callable(write_hook):
            return False

        content = self.consume_pending_answer_now_injection(agent_id)
        if not content:
            return False

        try:
            write_hook(content)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[Orchestrator] Failed priming Answer Now hook payload for {agent_id}: {e}",
                exc_info=True,
            )
            return False

        logger.info(
            f"[Orchestrator] Primed Answer Now hook payload for {agent_id} ({len(content)} chars)",
        )
        return True
