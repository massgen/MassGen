"""B1 regression tests: snapshot copy is offloaded off the event loop.

The audit found ``FilesystemManager.copy_snapshots_to_temp_workspace`` was an
``async def`` performing purely *synchronous* blocking I/O (rmtree/copytree/scrub)
directly on the asyncio event loop. While one agent's snapshots were copied, no
other agent's stream could be consumed -- the orchestrator's parallelism was
silently serialized.

These tests prove:
  1. The blocking work now runs on a worker thread (not the main/event-loop
     thread) -- i.e. it is offloaded via ``asyncio.to_thread``.
  2. The event loop stays responsive: another coroutine makes progress while the
     copy is in flight.
  3. Functional behavior is preserved byte-for-byte (anon-id dirs, excluded
     framework metadata dirs, content copied).

No external/LLM calls; uses real temp directories.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from massgen.filesystem_manager._filesystem_manager import FilesystemManager


def _make_fm(temp_workspace: Path, monkeypatch) -> FilesystemManager:
    """Build a minimal FilesystemManager exercising only the copy path."""
    fm = FilesystemManager.__new__(FilesystemManager)
    fm.agent_temporary_workspace = temp_workspace
    # The media-ledger normalization needs unrelated state; no-op it for isolation.
    monkeypatch.setattr(fm, "_normalize_media_call_ledger_paths", lambda **kwargs: None)
    return fm


def _seed_snapshot(root: Path, name: str) -> Path:
    snap = root / name
    (snap / "src").mkdir(parents=True)
    (snap / "src" / "main.py").write_text("print('hi')\n")
    (snap / "answer.md").write_text("# answer\n")
    # framework metadata that must be excluded from the temp copy
    (snap / ".git").mkdir()
    (snap / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (snap / ".massgen").mkdir()
    (snap / ".massgen" / "state.json").write_text("{}")
    return snap


@pytest.mark.asyncio
async def test_copy_runs_off_event_loop_thread(tmp_path, monkeypatch) -> None:
    """The blocking copy executes on a worker thread, not the main thread."""
    src_root = tmp_path / "snaps"
    src_root.mkdir()
    snap = _seed_snapshot(src_root, "agentA")

    temp_ws = tmp_path / "temp_ws"
    fm = _make_fm(temp_ws, monkeypatch)

    recorded: dict[str, threading.Thread] = {}
    import massgen.filesystem_manager._filesystem_manager as fsm

    real_copytree = fsm.shutil.copytree

    def _spy_copytree(*args, **kwargs):
        recorded["thread"] = threading.current_thread()
        return real_copytree(*args, **kwargs)

    monkeypatch.setattr(fsm.shutil, "copytree", _spy_copytree)

    result = await fm.copy_snapshots_to_temp_workspace({"agentA": snap}, {"agentA": "agent_1"})

    assert result == temp_ws
    assert "thread" in recorded, "copytree never ran"
    assert recorded["thread"] is not threading.main_thread(), "copy ran on the event-loop thread (not offloaded)"


@pytest.mark.asyncio
async def test_event_loop_stays_responsive_during_copy(tmp_path, monkeypatch) -> None:
    """A concurrent coroutine makes progress while the copy is blocking a worker thread."""
    src_root = tmp_path / "snaps"
    src_root.mkdir()
    snap = _seed_snapshot(src_root, "agentA")
    fm = _make_fm(tmp_path / "temp_ws", monkeypatch)

    import massgen.filesystem_manager._filesystem_manager as fsm

    real_copytree = fsm.shutil.copytree
    copy_started = threading.Event()
    release_copy = threading.Event()

    def _slow_copytree(*args, **kwargs):
        copy_started.set()
        # Block the worker thread; the event loop must keep running.
        release_copy.wait(timeout=5)
        return real_copytree(*args, **kwargs)

    monkeypatch.setattr(fsm.shutil, "copytree", _slow_copytree)

    ticks = 0

    async def _ticker():
        nonlocal ticks
        # Wait until the copy is actually mid-flight on the worker thread...
        while not copy_started.is_set():
            await asyncio.sleep(0.001)
        # ...then prove the loop still schedules us several times while it blocks.
        for _ in range(5):
            ticks += 1
            await asyncio.sleep(0.001)
        release_copy.set()

    copy_task = asyncio.create_task(fm.copy_snapshots_to_temp_workspace({"agentA": snap}, {"agentA": "agent_1"}))
    await asyncio.gather(copy_task, _ticker())

    assert ticks == 5, "event loop was blocked during the snapshot copy"


@pytest.mark.asyncio
async def test_copy_preserves_content_and_excludes_metadata(tmp_path, monkeypatch) -> None:
    """Anon-id destination, real content copied, framework metadata excluded."""
    src_root = tmp_path / "snaps"
    src_root.mkdir()
    snap = _seed_snapshot(src_root, "agentA")
    temp_ws = tmp_path / "temp_ws"
    fm = _make_fm(temp_ws, monkeypatch)

    await fm.copy_snapshots_to_temp_workspace({"agentA": snap}, {"agentA": "agent_1"})

    dest = temp_ws / "agent_1"
    assert (dest / "src" / "main.py").read_text() == "print('hi')\n"
    assert (dest / "answer.md").exists()
    assert not (dest / ".git").exists(), ".git must be excluded from temp copy"
    assert not (dest / ".massgen").exists(), ".massgen must be excluded from temp copy"


@pytest.mark.asyncio
async def test_copy_clears_stale_temp_workspace(tmp_path, monkeypatch) -> None:
    """A stale file from a prior round is removed before the new copy."""
    src_root = tmp_path / "snaps"
    src_root.mkdir()
    snap = _seed_snapshot(src_root, "agentA")
    temp_ws = tmp_path / "temp_ws"
    temp_ws.mkdir()
    (temp_ws / "stale.txt").write_text("old round")

    fm = _make_fm(temp_ws, monkeypatch)
    await fm.copy_snapshots_to_temp_workspace({"agentA": snap}, {"agentA": "agent_1"})

    assert not (temp_ws / "stale.txt").exists()
    assert (temp_ws / "agent_1" / "answer.md").exists()


@pytest.mark.asyncio
async def test_copy_returns_none_without_temp_workspace(monkeypatch) -> None:
    fm = FilesystemManager.__new__(FilesystemManager)
    fm.agent_temporary_workspace = None
    result = await fm.copy_snapshots_to_temp_workspace({}, {})
    assert result is None
