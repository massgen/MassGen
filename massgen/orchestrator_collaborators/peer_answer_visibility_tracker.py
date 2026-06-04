"""Peer answer visibility tracking, extracted from Orchestrator.

Owns the per-agent seen-answer revision bookkeeping that drives mid-stream
peer answer injection. All shared state (``agent_states[*].seen_answer_counts``,
``decomposition_answer_streak``, ``pending_checklist_recheck_labels``) is
mutated through the orchestrator back-ref so other collaborators (notably the
not-yet-extracted ChecklistGateManager) see one consistent live set.

Notes on invariants:
- ``_mark_pending_checklist_recheck_labels`` is a DUAL WRITER with the
  not-yet-extracted ChecklistGateManager (which writes the same field at
  orchestrator.py around lines 2216/2729). This collaborator always mutates
  via ``self._orchestrator.agent_states[...]`` so both writers share the live
  set when the gate manager is later extracted.
- ``midstream_injections_this_round`` is READ here but WRITTEN by the still-
  on-orchestrator MidStreamInjectionHookInstaller methods.
- Newest-first selection and the ``max_midstream_injections_per_round`` cap
  are preserved byte-for-byte (covered by test_novelty_injection.py and
  test_round_evaluator_loop.py).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class PeerAnswerVisibilityTracker:
    """Tracks which peer answer revisions an agent has seen for mid-stream injection."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def get_agent_answer_revision_count(self, agent_id: str) -> int:
        """Get total answer revisions submitted by an agent."""
        return len(self._orchestrator.coordination_tracker.answers_by_agent.get(agent_id, []))

    def get_answer_revision_counts(self) -> dict[str, int]:
        """Get current answer revision counts for all orchestrated agents."""
        orch = self._orchestrator
        return {aid: len(orch.coordination_tracker.answers_by_agent.get(aid, [])) for aid in orch.agents.keys()}

    def get_current_answers_snapshot(self) -> dict[str, str]:
        """Return latest submitted answer content for each agent that has one.

        In step mode, includes ALL session dir answers (including the real
        agent's own prior answer) so the agent sees everything anonymized.
        A new answer from the real agent takes precedence over the prior one.
        """
        orch = self._orchestrator
        snapshot = {aid: state.answer for aid, state in orch.agent_states.items() if state.answer}
        if orch._step_mode and orch._step_mode.enabled and orch._step_inputs:
            for va_id, va_state in orch._step_inputs.virtual_agents.items():
                if va_state.latest_answer is not None:
                    snapshot.setdefault(va_id, va_state.latest_answer)
        return snapshot

    def sync_decomposition_answer_visibility(self, agent_id: str) -> None:
        """Update seen-answer revision snapshot for an agent.

        In decomposition mode this also resets the consecutive answer streak
        when unseen external updates were observed.
        """
        orch = self._orchestrator
        state = orch.agent_states.get(agent_id)
        if not state:
            return

        current_counts = self.get_answer_revision_counts()
        saw_unseen_external_update = any(other_id != agent_id and current_count > state.seen_answer_counts.get(other_id, 0) for other_id, current_count in current_counts.items())

        if orch._is_decomposition_mode() and saw_unseen_external_update and state.decomposition_answer_streak > 0:
            logger.info(
                "[Orchestrator] Reset decomposition answer streak for %s after seeing external answer updates",
                agent_id,
            )
            state.decomposition_answer_streak = 0

        state.seen_answer_counts = current_counts

    def mark_seen_answer_revisions(
        self,
        agent_id: str,
        source_agent_ids: list[str],
        seen_counts: dict[str, int] | None = None,
    ) -> None:
        """Mark answer revisions from source agents as seen by ``agent_id``.

        ``seen_counts`` (R1 fix): per-source revision counts *captured at the
        moment the injected content was selected*. When provided, the source is
        marked seen up to that captured count rather than the live count, so a
        peer revision published during the intervening ``await`` (e.g. snapshot
        copy) is NOT silently marked seen and remains injectable. The captured
        count is clamped to the current count and never lowers an already-higher
        seen count. When omitted, falls back to the legacy live read.
        """
        orch = self._orchestrator
        state = orch.agent_states.get(agent_id)
        if not state:
            return
        for source_agent_id in source_agent_ids:
            current = self.get_agent_answer_revision_count(source_agent_id)
            if seen_counts is not None and source_agent_id in seen_counts:
                count = min(int(seen_counts[source_agent_id]), current)
            else:
                count = current
            prev = state.seen_answer_counts.get(source_agent_id, 0)
            state.seen_answer_counts[source_agent_id] = max(prev, count)

    def get_latest_answer_revision_timestamp(self, source_agent_id: str) -> float:
        """Get timestamp of the latest answer revision for an agent."""
        revisions = self._orchestrator.coordination_tracker.answers_by_agent.get(source_agent_id, [])
        if not revisions:
            return 0.0
        latest_revision = revisions[-1]
        return float(getattr(latest_revision, "timestamp", 0.0) or 0.0)

    def get_unseen_answer_update_candidates(
        self,
        agent_id: str,
        current_answers: dict[str, str],
    ) -> list[tuple[str, str, float]]:
        """Return unseen source answer updates sorted newest-first by revision timestamp."""
        orch = self._orchestrator
        state = orch.agent_states.get(agent_id)
        if not state:
            return []

        unseen_candidates: list[tuple[str, str, float]] = []
        for source_agent_id, answer_content in current_answers.items():
            # Never inject an agent's own answer back into itself.
            if source_agent_id == agent_id:
                continue

            seen_revision_count = state.seen_answer_counts.get(source_agent_id, 0)
            current_revision_count = self.get_agent_answer_revision_count(source_agent_id)
            if current_revision_count <= seen_revision_count:
                continue

            unseen_candidates.append(
                (
                    source_agent_id,
                    answer_content,
                    self.get_latest_answer_revision_timestamp(source_agent_id),
                ),
            )

        unseen_candidates.sort(key=lambda item: item[2], reverse=True)
        return unseen_candidates

    def get_unseen_source_agent_ids(self, agent_id: str) -> list[str]:
        """Return source agents whose latest revisions are unseen by ``agent_id``."""
        unseen_candidates = self.get_unseen_answer_update_candidates(
            agent_id,
            self.get_current_answers_snapshot(),
        )
        return [source_agent_id for source_agent_id, _, _ in unseen_candidates]

    def has_unseen_answer_updates(self, agent_id: str) -> bool:
        """Return True when ``agent_id`` still has unseen latest peer revisions."""
        return bool(self.get_unseen_source_agent_ids(agent_id))

    def select_midstream_answer_updates(
        self,
        agent_id: str,
        current_answers: dict[str, str],
    ) -> tuple[dict[str, str], bool]:
        """Select answer updates for mid-stream injection.

        Returns:
            Tuple of (selected_answers, had_unseen_updates). selected_answers
            may be empty if unseen updates exist but the fairness cap for this
            round is exhausted.
        """
        orch = self._orchestrator
        unseen_candidates = self.get_unseen_answer_update_candidates(
            agent_id,
            current_answers,
        )
        if not unseen_candidates:
            return ({}, False)

        state = orch.agent_states.get(agent_id)
        if not state:
            return ({}, True)

        selected_candidates = unseen_candidates
        if orch._is_fairness_enabled():
            cap = int(getattr(orch.config, "max_midstream_injections_per_round", 2))
            remaining_slots = max(cap - state.midstream_injections_this_round, 0)
            if remaining_slots <= 0:
                return ({}, True)
            selected_candidates = unseen_candidates[:remaining_slots]

        selected_answers = {source_agent_id: answer for source_agent_id, answer, _ in selected_candidates}
        return (selected_answers, True)

    @staticmethod
    def extract_submitted_agent_labels(scores_payload: Any) -> set[str]:
        """Extract first-level agent labels from a submit_checklist scores payload."""
        if not isinstance(scores_payload, dict):
            return set()
        if not scores_payload:
            return set()

        # Flat format (E1/E2/...) is not per-agent.
        top_level_keys = {str(k) for k in scores_payload.keys()}
        if any(k.startswith("E") or k.startswith("T") for k in top_level_keys):
            return set()
        return top_level_keys

    def mark_pending_checklist_recheck_labels(
        self,
        agent_id: str,
        source_agent_ids: list[str],
    ) -> None:
        """Record injected latest labels so one post-injection checklist recheck is allowed.

        DUAL WRITER: mutates ``state.pending_checklist_recheck_labels`` via the
        orchestrator back-ref so the not-yet-extracted ChecklistGateManager
        sees one consistent live set.
        """
        orch = self._orchestrator
        state = orch.agent_states.get(agent_id)
        if not state or not source_agent_ids:
            return

        agent = orch.agents.get(agent_id)
        backend = getattr(agent, "backend", None) if agent is not None else None
        supports_sdk = bool(getattr(backend, "supports_sdk_mcp", False))

        pending: set[str] = set()
        if supports_sdk:
            pending = set(getattr(state, "pending_checklist_recheck_labels", set()) or set())
        else:
            raw_pending: Any = None
            specs_path = getattr(backend, "_checklist_specs_path", None) if backend is not None else None
            if specs_path:
                try:
                    with open(specs_path, encoding="utf-8") as f:
                        specs_payload = json.load(f)
                    raw_pending = (specs_payload.get("state") or {}).get("pending_checklist_recheck_labels")
                except Exception:
                    raw_pending = None
            if raw_pending is None and backend is not None and hasattr(backend, "_checklist_state"):
                raw_pending = getattr(backend, "_checklist_state", {}).get("pending_checklist_recheck_labels", [])
            if isinstance(raw_pending, str):
                label = raw_pending.strip()
                if label:
                    pending.add(label)
            elif isinstance(raw_pending, (list, tuple, set)):
                for raw in raw_pending:
                    label = str(raw).strip()
                    if label:
                        pending.add(label)

        for source_agent_id in source_agent_ids:
            revisions = orch.coordination_tracker.answers_by_agent.get(source_agent_id, [])
            if not revisions:
                continue
            latest_label = getattr(revisions[-1], "label", None)
            if latest_label:
                pending.add(str(latest_label))
        # Mutate via back-ref so any other writer (future ChecklistGateManager)
        # sees the same live set.
        setattr(state, "pending_checklist_recheck_labels", pending)
        if backend is not None and hasattr(backend, "_checklist_state"):
            backend._checklist_state["pending_checklist_recheck_labels"] = sorted(pending)
            if not supports_sdk and hasattr(backend, "_checklist_specs_path"):
                try:
                    from massgen.mcp_tools.checklist_tools_server import (
                        write_checklist_specs,
                    )

                    write_checklist_specs(
                        items=getattr(backend, "_checklist_items", []),
                        state=backend._checklist_state,
                        output_path=backend._checklist_specs_path,
                    )
                except Exception:
                    logger.debug(
                        "[Orchestrator] Unable to persist pending checklist recheck labels for %s",
                        agent_id,
                        exc_info=True,
                    )

    def register_injected_answer_updates(
        self,
        agent_id: str,
        source_agent_ids: list[str],
        seen_counts: dict[str, int] | None = None,
    ) -> None:
        """Apply per-agent state updates after mid-stream answer injection.

        ``seen_counts`` is forwarded to :meth:`mark_seen_answer_revisions` (R1
        fix): pass the revision counts captured when the injected content was
        selected so a peer revision published during the intervening ``await``
        is not marked seen. See that method for details.
        """
        orch = self._orchestrator
        state = orch.agent_states.get(agent_id)
        if not state or not source_agent_ids:
            return

        external_sources = [source_id for source_id in source_agent_ids if source_id != agent_id]
        if orch._is_decomposition_mode() and external_sources and state.decomposition_answer_streak > 0:
            logger.info(
                "[Orchestrator] Reset decomposition answer streak for %s after mid-stream answer injection",
                agent_id,
            )
            state.decomposition_answer_streak = 0

        self.mark_seen_answer_revisions(agent_id, source_agent_ids, seen_counts=seen_counts)
