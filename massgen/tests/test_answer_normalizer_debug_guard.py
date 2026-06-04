"""C2 regression: the workspace-path normalizer must not eagerly build debug
strings when no DEBUG sink is attached.

The two debug logs in ``normalize_workspace_paths_in_answers`` interpolate the
full answer body on every (answer x agent) pair. They now use loguru brace-style
deferred formatting, so loguru only renders the message when a handler actually
accepts the record. These tests assert (a) no formatting work happens without a
DEBUG sink, (b) the message renders correctly when a sink is attached, and
(c) functional path-rewriting output is preserved.
"""

from __future__ import annotations

import types

from massgen.logger_config import logger
from massgen.orchestrator_collaborators.answer_text_normalizer import (
    AnswerTextNormalizer,
)


def _make_orch(workspace: str) -> types.SimpleNamespace:
    fs = types.SimpleNamespace(
        agent_temporary_workspace="/tmp/agentview",
        get_current_workspace=lambda: workspace,
    )
    backend = types.SimpleNamespace(filesystem_manager=fs)
    agent = types.SimpleNamespace(backend=backend)
    orch = types.SimpleNamespace()
    orch.agents = {"peer": agent, "viewer": agent}
    orch.coordination_tracker = types.SimpleNamespace(
        get_reverse_agent_mapping=lambda: {"peer": "agent_1", "viewer": "agent_2"},
    )
    return orch


def test_c2_output_preserved_and_path_rewritten() -> None:
    orch = _make_orch("/work/peer")
    normalizer = AnswerTextNormalizer(orch)

    out = normalizer.normalize_workspace_paths_in_answers(
        {"peer": "see /work/peer/file.py"},
        viewing_agent_id="viewer",
    )

    assert "/work/peer" not in out["peer"], "workspace path was not rewritten"


def test_c2_message_renders_when_sink_attached() -> None:
    """With a DEBUG sink, the deferred message renders with the substituted args."""
    orch = _make_orch("/work/peer")
    normalizer = AnswerTextNormalizer(orch)

    captured: list[str] = []
    sink_id = logger.add(lambda m: captured.append(str(m)), level="DEBUG")
    try:
        normalizer.normalize_workspace_paths_in_answers(
            {"peer": "see /work/peer/file.py"},
            viewing_agent_id="viewer",
        )
    finally:
        logger.remove(sink_id)

    joined = "\n".join(captured)
    assert "Replacing /work/peer" in joined
    assert "original answer: see /work/peer/file.py" in joined


def test_c2_answer_body_not_formatted_without_debug_sink() -> None:
    """Without a DEBUG sink, the answer object is never formatted (deferred)."""

    class _Tripwire(str):
        formats = 0

        def __format__(self, spec: str) -> str:  # pragma: no cover - asserted via counter
            type(self).formats += 1
            return str.__format__(self, spec)

    _Tripwire.formats = 0
    orch = _make_orch("/work/peer")
    normalizer = AnswerTextNormalizer(orch)

    # No DEBUG sink attached: loguru must not format the (expensive) answer arg.
    normalizer.normalize_workspace_paths_in_answers(
        {"peer": _Tripwire("see /work/peer/file.py")},
        viewing_agent_id="viewer",
    )

    assert _Tripwire.formats == 0, "answer body was formatted despite no DEBUG sink (eager logging)"
