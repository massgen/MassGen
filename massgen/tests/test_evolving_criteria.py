"""Tests for the evolving evaluation criteria feature.

Covers:
- Config wiring (agent_config.py + cli.py)
- _should_evolve_criteria gate logic
- _collect_evolution_input_data
- _build_criteria_evolution_proposal_task / synthesis task
- parse_evolution_response (utility in evaluation_criteria_generator.py)
- _apply/_write_criteria_evolution_memory
- Full gate integration (mocked subagent spawns)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeCoordinationConfig:
    evolving_criteria: bool = True
    evolving_criteria_score_threshold: int = 8
    evolving_criteria_max_evolutions: int = 2
    evolving_criteria_min_high_score_count: int = 2
    evolving_criteria_timeout: int = 300


@dataclass
class _FakeConfig:
    coordination_config: _FakeCoordinationConfig = field(
        default_factory=_FakeCoordinationConfig,
    )
    voting_sensitivity: str = "checklist_gated"
    voting_threshold: int = 5
    max_new_answers_per_agent: int = 5


@dataclass
class _FakeAgentState:
    restart_count: int = 1
    answer: str | None = "draft answer"
    checklist_history: list[dict[str, Any]] = field(default_factory=list)


class _FakeFilesystemManager:
    def __init__(self, tmp: Path) -> None:
        self.snapshot_storage = tmp / "snapshots"
        self.snapshot_storage.mkdir(parents=True, exist_ok=True)
        self.cwd = tmp / "workspace"
        self.cwd.mkdir(parents=True, exist_ok=True)


class _FakeBackend:
    def __init__(self, fs_mgr: _FakeFilesystemManager) -> None:
        self.filesystem_manager = fs_mgr


class _FakeAgent:
    def __init__(self, backend: _FakeBackend) -> None:
        self.backend = backend


def _make_criteria(count: int = 3) -> list:
    from massgen.evaluation_criteria_generator import GeneratedCriterion

    return [
        GeneratedCriterion(
            id=f"E{i + 1}",
            text=f"Criterion {i + 1}: agents should do X with quality Y",
            category="standard" if i > 0 else "primary",
            anti_patterns=[f"failure mode {i + 1}"],
            score_anchors={
                "3": f"poor-{i + 1}",
                "5": f"ok-{i + 1}",
                "7": f"good-{i + 1}",
                "9": f"excellent-{i + 1}",
            },
        )
        for i in range(count)
    ]


def _make_high_score_history(criterion_count: int = 3, score: int = 9) -> list[dict[str, Any]]:
    """Return a checklist_history with all criteria scoring `score`."""
    return [
        {
            "verdict": "new_answer",
            "true_count": criterion_count,
            "total_score": score * criterion_count,
            "items_detail": [{"id": f"E{i + 1}", "score": score, "reasoning": "great"} for i in range(criterion_count)],
        },
    ]


def _make_low_score_history(criterion_count: int = 3, score: int = 5) -> list[dict[str, Any]]:
    """Return a checklist_history with all criteria scoring `score`."""
    return [
        {
            "verdict": "new_answer",
            "true_count": 0,
            "total_score": score * criterion_count,
            "items_detail": [{"id": f"E{i + 1}", "score": score, "reasoning": "meh"} for i in range(criterion_count)],
        },
    ]


def _make_orchestrator(
    tmp_path: Path,
    *,
    evolving: bool = True,
    restart_count: int = 1,
    high_scores: bool = True,
    n_agents: int = 1,
):
    from massgen.orchestrator import Orchestrator

    agents = {}
    states = {}
    for i in range(n_agents):
        aid = f"agent_{chr(ord('a') + i)}"
        fs_mgr = _FakeFilesystemManager(tmp_path / aid)
        agents[aid] = _FakeAgent(_FakeBackend(fs_mgr))
        state = _FakeAgentState(
            restart_count=restart_count,
            checklist_history=_make_high_score_history() if high_scores else _make_low_score_history(),
        )
        states[aid] = state

    config = _FakeConfig(
        coordination_config=_FakeCoordinationConfig(evolving_criteria=evolving),
    )

    with patch.object(Orchestrator, "__init__", lambda self, **kw: None):
        orch = Orchestrator()

    orch.config = config
    orch.agents = agents
    orch.agent_states = states
    orch._background_trace_tasks = {}
    orch._pending_subagent_results = {}
    orch._original_task = "Write a landing page"
    orch._criteria_evolution_count = 0
    orch._criteria_evolution_completed_labels = set()
    orch._criteria_evolution_history = []
    orch._generated_evaluation_criteria = _make_criteria()
    orch._evaluation_criteria_generated = True
    orch._round_start_context_blocks = {}
    orch.coordination_ui = None
    orch._notify_precollab_completed = MagicMock()
    return orch


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------


def test_parse_coordination_config_wires_evolving_criteria():
    from massgen.cli import _parse_coordination_config

    result = _parse_coordination_config({"evolving_criteria": True})
    assert result.evolving_criteria is True


def test_evolving_criteria_defaults_to_false():
    from massgen.agent_config import CoordinationConfig

    assert CoordinationConfig().evolving_criteria is False


def test_evolving_criteria_score_threshold_default():
    from massgen.agent_config import CoordinationConfig

    assert CoordinationConfig().evolving_criteria_score_threshold == 8


def test_evolving_criteria_max_evolutions_default():
    from massgen.agent_config import CoordinationConfig

    assert CoordinationConfig().evolving_criteria_max_evolutions == 2


def test_evolving_criteria_timeout_default():
    from massgen.agent_config import CoordinationConfig

    assert CoordinationConfig().evolving_criteria_timeout == 300


def test_parse_coordination_config_wires_all_evolving_fields():
    from massgen.cli import _parse_coordination_config

    result = _parse_coordination_config(
        {
            "evolving_criteria": True,
            "evolving_criteria_score_threshold": 7,
            "evolving_criteria_max_evolutions": 3,
            "evolving_criteria_min_high_score_count": 1,
            "evolving_criteria_timeout": 600,
        },
    )
    assert result.evolving_criteria is True
    assert result.evolving_criteria_score_threshold == 7
    assert result.evolving_criteria_max_evolutions == 3
    assert result.evolving_criteria_min_high_score_count == 1
    assert result.evolving_criteria_timeout == 600


# ---------------------------------------------------------------------------
# _should_evolve_criteria gate logic
# ---------------------------------------------------------------------------


def test_should_evolve_returns_false_when_disabled(tmp_path):
    orch = _make_orchestrator(tmp_path, evolving=False)
    assert orch._should_evolve_criteria() is False


def test_should_evolve_returns_false_round1(tmp_path):
    """Round 1 (restart_count=0) should not trigger evolution."""
    orch = _make_orchestrator(tmp_path, restart_count=0)
    assert orch._should_evolve_criteria() is False


def test_should_evolve_returns_false_no_criteria_at_all(tmp_path):
    """No criteria from any source → no evolution."""
    orch = _make_orchestrator(tmp_path)
    orch._generated_evaluation_criteria = None
    # Mock bootstrap to return nothing (no criteria from any source)
    orch._resolve_effective_checklist_criteria = MagicMock(
        return_value=(None, None, None, None, None, None),
    )
    assert orch._should_evolve_criteria() is False


def test_should_evolve_bootstraps_from_inline_criteria(tmp_path):
    """With inline criteria and no generator, evolution should still trigger."""
    orch = _make_orchestrator(tmp_path)
    orch._generated_evaluation_criteria = None  # no generator ran
    orch.config.coordination_config.checklist_criteria_inline = [
        {"id": "E1", "text": "criterion one"},
        {"id": "E2", "text": "criterion two"},
        {"id": "E3", "text": "criterion three"},
    ]
    assert orch._should_evolve_criteria() is True
    assert orch._generated_evaluation_criteria is not None
    assert len(orch._generated_evaluation_criteria) == 3


def test_should_evolve_bootstraps_from_default_criteria(tmp_path):
    """Even with no generator/inline/preset, default checklist criteria get bootstrapped."""
    orch = _make_orchestrator(tmp_path)
    orch._generated_evaluation_criteria = None
    # No inline, no preset — relies on default criteria from _resolve_effective_checklist_criteria
    assert orch._should_evolve_criteria() is True
    assert orch._generated_evaluation_criteria is not None
    assert len(orch._generated_evaluation_criteria) > 0


def test_should_evolve_returns_false_max_reached(tmp_path):
    orch = _make_orchestrator(tmp_path)
    orch._criteria_evolution_count = 2  # at default max
    assert orch._should_evolve_criteria() is False


def test_should_evolve_returns_false_low_scores(tmp_path):
    orch = _make_orchestrator(tmp_path, high_scores=False)
    assert orch._should_evolve_criteria() is False


def test_should_evolve_returns_true_high_scores(tmp_path):
    orch = _make_orchestrator(tmp_path, high_scores=True)
    assert orch._should_evolve_criteria() is True


def test_should_evolve_idempotency_guard(tmp_path):
    """Same answer labels should not trigger re-evolution."""
    orch = _make_orchestrator(tmp_path, high_scores=True)
    current_answers = {"a1": "answer"}
    orch._criteria_evolution_completed_labels.add(("a1",))
    assert orch._should_evolve_criteria(current_answers=current_answers) is False


def test_should_evolve_min_high_score_count(tmp_path):
    """Should require at least N criteria at/above threshold."""
    orch = _make_orchestrator(tmp_path)
    # Only one criterion scores 9, but min_high_score_count=2
    orch.agent_states["agent_a"].checklist_history = [
        {
            "verdict": "new_answer",
            "total_score": 15,
            "items_detail": [
                {"id": "E1", "score": 9},
                {"id": "E2", "score": 4},
                {"id": "E3", "score": 4},
            ],
        },
    ]
    assert orch._should_evolve_criteria() is False


# ---------------------------------------------------------------------------
# _collect_evolution_input_data
# ---------------------------------------------------------------------------


def test_collect_data_includes_all_agents(tmp_path):
    orch = _make_orchestrator(tmp_path, n_agents=2)
    data = orch._collect_evolution_input_data()
    assert set(data["trace_paths"].keys()) == set(orch.agents.keys())
    assert set(data["checklist_histories"].keys()) == set(orch.agents.keys())


def test_collect_data_includes_current_criteria(tmp_path):
    orch = _make_orchestrator(tmp_path)
    data = orch._collect_evolution_input_data()
    assert len(data["current_criteria"]) == 3


def test_collect_data_returns_trace_path_when_exists(tmp_path):
    orch = _make_orchestrator(tmp_path)
    fs_mgr = orch.agents["agent_a"].backend.filesystem_manager
    trace_path = fs_mgr.snapshot_storage / "execution_trace.md"
    trace_path.write_text("# Round 1 trace\nTool call A...", encoding="utf-8")
    data = orch._collect_evolution_input_data()
    assert data["trace_paths"]["agent_a"] == trace_path


def test_collect_data_missing_trace_returns_none(tmp_path):
    orch = _make_orchestrator(tmp_path)
    data = orch._collect_evolution_input_data()
    assert data["trace_paths"]["agent_a"] is None


def test_collect_data_trace_path_absolute_for_relative_snapshot_storage(tmp_path, monkeypatch):
    """Trace path must be absolute even when snapshot_storage is a relative Path.

    Regression: production sets snapshot_storage as Path(".massgen/snapshots/<session>/agent_a")
    which is relative. _get_execution_trace_path_for_agent returns this as-is. When passed
    as a context_path to _preprocess_spawn_tasks, relative paths are resolved against
    workspace_root (the agent workspace dir) instead of the process CWD. Since the file lives
    under CWD/.massgen/... not under workspace_root/.massgen/..., the exists() check fails
    and the spawn returns an error dict — producing "No valid criteria evolution proposals".
    """
    monkeypatch.chdir(tmp_path)

    orch = _make_orchestrator(tmp_path)
    fs_mgr = orch.agents["agent_a"].backend.filesystem_manager

    # Simulate the production case: relative snapshot_storage
    rel_storage = Path(".massgen") / "snapshots" / "test_session" / "agent_a"
    abs_storage = tmp_path / rel_storage
    abs_storage.mkdir(parents=True, exist_ok=True)
    fs_mgr.snapshot_storage = rel_storage  # relative, just like real orchestrator

    (abs_storage / "execution_trace.md").write_text("# round 1 trace", encoding="utf-8")

    data = orch._collect_evolution_input_data()
    result_path = data["trace_paths"]["agent_a"]

    assert result_path is not None, "Trace file exists — path should not be None"
    assert result_path.is_absolute(), (
        f"Expected absolute path, got relative: {result_path!r}. "
        "A relative path from snapshot_storage gets mis-resolved against "
        "workspace_root in _preprocess_spawn_tasks, so the spawn silently fails."
    )


# ---------------------------------------------------------------------------
# Task building
# ---------------------------------------------------------------------------


def test_build_proposal_task_includes_criteria_and_scores(tmp_path):
    orch = _make_orchestrator(tmp_path)
    # Write a trace file so the path shows up
    fs_mgr = orch.agents["agent_a"].backend.filesystem_manager
    trace_path = fs_mgr.snapshot_storage / "execution_trace.md"
    trace_path.write_text("# trace", encoding="utf-8")
    evolution_data = orch._collect_evolution_input_data()
    task = orch._build_criteria_evolution_proposal_task("agent_a", evolution_data)
    assert "Criterion 1" in task  # from criteria text
    assert "E1=" in task  # from score history table
    # Trace referenced by path, not embedded
    assert str(trace_path) in task
    assert "# trace" not in task  # content not inlined


def test_build_synthesis_task_includes_proposals(tmp_path):
    orch = _make_orchestrator(tmp_path)
    criteria = _make_criteria()
    proposals = [{"analysis": "E1 is too easy", "evolved_criteria": []}, {"analysis": "raise E2", "evolved_criteria": []}]
    task = orch._build_criteria_evolution_synthesis_task(proposals, criteria, "write a page")
    assert "Proposal 1" in task
    assert "Proposal 2" in task
    assert "write a page" in task


# ---------------------------------------------------------------------------
# parse_evolution_response
# ---------------------------------------------------------------------------


def _make_evolution_json(*, unchanged_ids=None, evolved=None, status=None):
    if status == "UNCHANGED":
        return json.dumps({"status": "UNCHANGED", "analysis": "all good"})
    payload = {
        "status": "evolved",
        "unchanged_ids": unchanged_ids or [],
        "evolved_criteria": evolved or [],
        "evolution_summary": "E1 was raised to demand deeper originality",
    }
    return json.dumps(payload)


def test_parse_evolution_unchanged_sentinel():
    from massgen.evaluation_criteria_generator import parse_evolution_response

    response = _make_evolution_json(status="UNCHANGED")
    criteria, summary, is_unchanged = parse_evolution_response(response, _make_criteria())
    assert is_unchanged is True
    assert criteria is None
    assert summary is None


def test_parse_evolution_valid_json():
    from massgen.evaluation_criteria_generator import parse_evolution_response

    current = _make_criteria(3)
    evolved_item = {
        "id": "E1",
        "text": "Elevated E1 text — must be deeply original",
        "category": "primary",
        "anti_patterns": ["generic text"],
        "score_anchors": {"3": "boring", "5": "ok", "7": "interesting", "9": "outstanding"},
    }
    response = _make_evolution_json(unchanged_ids=["E2", "E3"], evolved=[evolved_item])
    criteria, summary, is_unchanged = parse_evolution_response(response, current)
    assert is_unchanged is False
    assert criteria is not None
    assert len(criteria) == 3
    # E1 was evolved
    assert "deeply original" in criteria[0].text
    # E2 and E3 kept
    assert "Criterion 2" in criteria[1].text
    assert "Criterion 3" in criteria[2].text


def test_parse_evolution_from_markdown_code_block():
    from massgen.evaluation_criteria_generator import parse_evolution_response

    current = _make_criteria(2)
    evolved_item = {
        "id": "E1",
        "text": "Evolved E1",
        "category": "standard",
        "anti_patterns": ["bad"],
        "score_anchors": {"3": "bad", "5": "mid", "7": "good", "9": "excellent"},
    }
    payload = {
        "status": "evolved",
        "unchanged_ids": ["E2"],
        "evolved_criteria": [evolved_item],
        "evolution_summary": "E1 raised",
    }
    response = f"Here is the JSON:\n```json\n{json.dumps(payload)}\n```"
    criteria, summary, is_unchanged = parse_evolution_response(response, current)
    assert is_unchanged is False
    assert criteria is not None
    assert criteria[0].text == "Evolved E1"


def test_parse_evolution_merges_unchanged_criteria():
    from massgen.evaluation_criteria_generator import parse_evolution_response

    current = _make_criteria(4)
    evolved_item = {
        "id": "E3",
        "text": "Evolved E3 text",
        "category": "standard",
        "anti_patterns": [],
        "score_anchors": {"3": "bad", "5": "mid", "7": "good", "9": "great"},
    }
    response = _make_evolution_json(unchanged_ids=["E1", "E2", "E4"], evolved=[evolved_item])
    criteria, summary, is_unchanged = parse_evolution_response(response, current)
    assert is_unchanged is False
    assert len(criteria) == 4
    # E3 was replaced
    assert criteria[2].text == "Evolved E3 text"
    # Others unchanged
    assert criteria[0].text == current[0].text
    assert criteria[1].text == current[1].text
    assert criteria[3].text == current[3].text


def test_parse_evolution_reassigns_ids():
    from massgen.evaluation_criteria_generator import parse_evolution_response

    current = _make_criteria(3)
    evolved_item = {
        "id": "E2",
        "text": "Evolved E2",
        "category": "standard",
        "anti_patterns": [],
        "score_anchors": {"3": "bad", "5": "ok", "7": "good", "9": "great"},
    }
    response = _make_evolution_json(unchanged_ids=["E1", "E3"], evolved=[evolved_item])
    criteria, _, _ = parse_evolution_response(response, current)
    assert [c.id for c in criteria] == ["E1", "E2", "E3"]


def test_parse_evolution_bad_json_returns_none():
    from massgen.evaluation_criteria_generator import parse_evolution_response

    criteria, summary, is_unchanged = parse_evolution_response("not json at all", _make_criteria())
    assert criteria is None
    assert is_unchanged is False


# ---------------------------------------------------------------------------
# _write_criteria_evolution_memory
# ---------------------------------------------------------------------------


def test_write_criteria_evolution_memory_creates_file(tmp_path):
    orch = _make_orchestrator(tmp_path)
    old = _make_criteria(3)
    new_c = _make_criteria(3)
    new_c[0].text = "Evolved E1 text"
    orch._write_criteria_evolution_memory(
        evolution_number=1,
        old_criteria=old,
        new_criteria=new_c,
        summary="E1 was raised to demand originality.",
    )
    memory_dir = orch.agents["agent_a"].backend.filesystem_manager.cwd / "memory" / "short_term"
    target = memory_dir / "criteria_evolution_1.md"
    assert target.exists()


def test_write_criteria_evolution_memory_has_frontmatter(tmp_path):
    orch = _make_orchestrator(tmp_path)
    old = _make_criteria(2)
    new_c = _make_criteria(2)
    orch._write_criteria_evolution_memory(1, old, new_c, "minor update")
    memory_dir = orch.agents["agent_a"].backend.filesystem_manager.cwd / "memory" / "short_term"
    content = (memory_dir / "criteria_evolution_1.md").read_text()
    assert content.startswith("---")
    assert "tier: short_term" in content


def test_write_criteria_evolution_memory_includes_diff(tmp_path):
    orch = _make_orchestrator(tmp_path)
    old = _make_criteria(2)
    new_c = _make_criteria(2)
    new_c[0].text = "Completely new E1 text"
    orch._write_criteria_evolution_memory(1, old, new_c, "E1 elevated")
    memory_dir = orch.agents["agent_a"].backend.filesystem_manager.cwd / "memory" / "short_term"
    content = (memory_dir / "criteria_evolution_1.md").read_text()
    assert "Completely new E1 text" in content
    assert "evolved" in content.lower()


# ---------------------------------------------------------------------------
# Integration: _run_criteria_evolution_if_needed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_gate_returns_true_when_disabled(tmp_path):
    orch = _make_orchestrator(tmp_path, evolving=False)
    result = await orch._run_criteria_evolution_if_needed({"a": "answer"})
    assert result is True


@pytest.mark.asyncio
async def test_evolution_gate_skips_when_low_scores(tmp_path):
    orch = _make_orchestrator(tmp_path, high_scores=False)
    # _should_evolve_criteria returns False → gate is a no-op
    result = await orch._run_criteria_evolution_if_needed({"a": "answer"})
    assert result is True
    assert orch._criteria_evolution_count == 0


@pytest.mark.asyncio
async def test_evolution_gate_runs_and_updates_criteria(tmp_path):
    orch = _make_orchestrator(tmp_path, high_scores=True)
    orch._get_current_answers_snapshot = MagicMock(return_value={"a1": "answer text"})

    evolved_item = {
        "id": "E1",
        "text": "Elevated E1: must demonstrate deep originality",
        "category": "primary",
        "anti_patterns": ["generic text"],
        "score_anchors": {"3": "boring", "5": "ok", "7": "interesting", "9": "outstanding"},
    }
    synthesis_output = json.dumps(
        {
            "status": "evolved",
            "unchanged_ids": ["E2", "E3"],
            "evolved_criteria": [evolved_item],
            "evolution_summary": "E1 was raised to demand deeper originality.",
        },
    )

    proposal_result = {
        "success": True,
        "results": [
            {
                "subagent_id": "criteria_evolver_1_0",
                "answer": json.dumps({"analysis": "E1 too easy", "evolved_criteria": [evolved_item], "unchanged_ids": ["E2", "E3"], "evolution_summary": "raise E1"}),
            },
        ],
    }
    synthesis_result = {
        "success": True,
        "results": [{"subagent_id": "criteria_evolution_synthesizer_1", "answer": synthesis_output}],
    }

    call_count = 0

    async def _mock_spawn(parent_agent_id, tasks, refine=True):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return proposal_result
        return synthesis_result

    orch._direct_spawn_subagents = _mock_spawn
    # Suppress _init_checklist_tool (it requires full orchestrator setup)
    orch._init_checklist_tool = MagicMock()
    # Suppress memory write since it needs real filesystem paths wired correctly
    # (already tested separately above)

    result = await orch._run_criteria_evolution_if_needed({"a1": "answer text"})
    assert result is True
    assert orch._criteria_evolution_count == 1
    assert orch._generated_evaluation_criteria[0].text == "Elevated E1: must demonstrate deep originality"


@pytest.mark.asyncio
async def test_evolution_gate_unchanged_sentinel_skips_update(tmp_path):
    orch = _make_orchestrator(tmp_path, high_scores=True)
    orch._get_current_answers_snapshot = MagicMock(return_value={"a1": "answer"})

    proposal_result = {
        "success": True,
        "results": [{"subagent_id": "criteria_evolver_1_0", "answer": json.dumps({"status": "UNCHANGED", "analysis": "all good"})}],
    }
    synthesis_result = {
        "success": True,
        "results": [{"subagent_id": "criteria_evolution_synthesizer_1", "answer": json.dumps({"status": "UNCHANGED", "analysis": "criteria fine"})}],
    }

    call_count = 0

    async def _mock_spawn(parent_agent_id, tasks, refine=True):
        nonlocal call_count
        call_count += 1
        return proposal_result if call_count == 1 else synthesis_result

    orch._direct_spawn_subagents = _mock_spawn
    original_criteria_text = orch._generated_evaluation_criteria[0].text

    result = await orch._run_criteria_evolution_if_needed({"a1": "answer"})
    assert result is True
    assert orch._criteria_evolution_count == 0  # unchanged → no increment
    assert orch._generated_evaluation_criteria[0].text == original_criteria_text


# ---------------------------------------------------------------------------
# File-based output: workspace/deliverable/evolved_criteria.json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_gate_reads_proposal_from_workspace_file(tmp_path):
    """Evolver writes JSON to deliverable/evolved_criteria.json; orchestrator reads it."""
    orch = _make_orchestrator(tmp_path, high_scores=True)

    evolved_item = {
        "id": "E1",
        "text": "Elevated E1 via workspace file",
        "category": "primary",
        "anti_patterns": ["generic"],
        "score_anchors": {"3": "bad", "5": "ok", "7": "good", "9": "great"},
    }
    proposal_json = {
        "analysis": "E1 became trivial",
        "unchanged_ids": ["E2", "E3"],
        "evolved_criteria": [evolved_item],
        "evolution_summary": "raised E1",
    }
    synthesis_json = {
        "status": "evolved",
        "unchanged_ids": ["E2", "E3"],
        "evolved_criteria": [evolved_item],
        "evolution_summary": "E1 raised via file",
    }

    # Build fake workspace dirs with deliverable/evolved_criteria.json
    proposal_ws = tmp_path / "criteria_evolver_ws"
    (proposal_ws / "deliverable").mkdir(parents=True)
    (proposal_ws / "deliverable" / "evolved_criteria.json").write_text(
        json.dumps(proposal_json),
        encoding="utf-8",
    )
    synth_ws = tmp_path / "synthesizer_ws"
    (synth_ws / "deliverable").mkdir(parents=True)
    (synth_ws / "deliverable" / "evolved_criteria.json").write_text(
        json.dumps(synthesis_json),
        encoding="utf-8",
    )

    # Mock spawn: return workspace paths, NO answer text
    proposal_result = {
        "success": True,
        "results": [{"subagent_id": "criteria_evolver_1_0", "answer": "", "workspace": str(proposal_ws)}],
    }
    synthesis_result = {
        "success": True,
        "results": [{"subagent_id": "criteria_evolution_synthesizer_1", "answer": "", "workspace": str(synth_ws)}],
    }
    call_count = 0

    async def _mock_spawn(parent_agent_id, tasks, refine=True):
        nonlocal call_count
        call_count += 1
        return proposal_result if call_count == 1 else synthesis_result

    orch._direct_spawn_subagents = _mock_spawn
    orch._init_checklist_tool = MagicMock()

    result = await orch._run_criteria_evolution_if_needed({"a1": "answer text"})
    assert result is True
    assert orch._criteria_evolution_count == 1
    assert orch._generated_evaluation_criteria[0].text == "Elevated E1 via workspace file"


@pytest.mark.asyncio
async def test_evolution_gate_workspace_file_takes_precedence_over_answer(tmp_path):
    """Workspace file beats answer text when both are present."""
    orch = _make_orchestrator(tmp_path, high_scores=True)

    file_evolved_item = {
        "id": "E1",
        "text": "FROM FILE",
        "category": "primary",
        "anti_patterns": [],
        "score_anchors": {"3": "a", "5": "b", "7": "c", "9": "d"},
    }
    answer_evolved_item = {**file_evolved_item, "text": "FROM ANSWER"}
    proposal_json = {"analysis": "file", "unchanged_ids": ["E2", "E3"], "evolved_criteria": [file_evolved_item], "evolution_summary": "file"}
    synthesis_json = {"status": "evolved", "unchanged_ids": ["E2", "E3"], "evolved_criteria": [file_evolved_item], "evolution_summary": "file wins"}

    ws = tmp_path / "evo_ws"
    (ws / "deliverable").mkdir(parents=True)
    (ws / "deliverable" / "evolved_criteria.json").write_text(json.dumps(proposal_json), encoding="utf-8")
    synth_ws = tmp_path / "synth_ws"
    (synth_ws / "deliverable").mkdir(parents=True)
    (synth_ws / "deliverable" / "evolved_criteria.json").write_text(json.dumps(synthesis_json), encoding="utf-8")

    call_count = 0

    async def _mock_spawn(parent_agent_id, tasks, refine=True):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"success": True, "results": [{"subagent_id": "x", "answer": json.dumps({**proposal_json, "evolved_criteria": [answer_evolved_item]}), "workspace": str(ws)}]}
        return {"success": True, "results": [{"subagent_id": "y", "answer": json.dumps({**synthesis_json, "evolved_criteria": [answer_evolved_item]}), "workspace": str(synth_ws)}]}

    orch._direct_spawn_subagents = _mock_spawn
    orch._init_checklist_tool = MagicMock()

    await orch._run_criteria_evolution_if_needed({"a1": "x"})
    assert orch._generated_evaluation_criteria[0].text == "FROM FILE"


@pytest.mark.asyncio
async def test_evolution_gate_finds_file_in_nested_agent_workspace(tmp_path):
    """In production the file lands at agent_1_*/deliverable/evolved_criteria.json,
    not at the workspace root. The reader must search nested agent dirs."""
    orch = _make_orchestrator(tmp_path, high_scores=True)

    evolved_item = {
        "id": "E1",
        "text": "Nested agent workspace hit",
        "category": "primary",
        "anti_patterns": [],
        "score_anchors": {"3": "a", "5": "b", "7": "c", "9": "d"},
    }
    proposal_json = {"analysis": "nested", "unchanged_ids": ["E2", "E3"], "evolved_criteria": [evolved_item], "evolution_summary": "nested"}
    synthesis_json = {"status": "evolved", "unchanged_ids": ["E2", "E3"], "evolved_criteria": [evolved_item], "evolution_summary": "nested synth"}

    # Mimic real layout: workspace/agent_1_abc123/deliverable/evolved_criteria.json
    ws = tmp_path / "evo_nested_ws"
    (ws / "agent_1_abc123" / "deliverable").mkdir(parents=True)
    (ws / "agent_1_abc123" / "deliverable" / "evolved_criteria.json").write_text(
        json.dumps(proposal_json),
        encoding="utf-8",
    )
    synth_ws = tmp_path / "synth_nested_ws"
    (synth_ws / "agent_1_xyz" / "deliverable").mkdir(parents=True)
    (synth_ws / "agent_1_xyz" / "deliverable" / "evolved_criteria.json").write_text(
        json.dumps(synthesis_json),
        encoding="utf-8",
    )

    call_count = 0

    async def _mock_spawn(parent_agent_id, tasks, refine=True):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"success": True, "results": [{"subagent_id": "x", "answer": "", "workspace": str(ws)}]}
        return {"success": True, "results": [{"subagent_id": "y", "answer": "", "workspace": str(synth_ws)}]}

    orch._direct_spawn_subagents = _mock_spawn
    orch._init_checklist_tool = MagicMock()

    await orch._run_criteria_evolution_if_needed({"a1": "x"})
    assert orch._criteria_evolution_count == 1
    assert orch._generated_evaluation_criteria[0].text == "Nested agent workspace hit"
