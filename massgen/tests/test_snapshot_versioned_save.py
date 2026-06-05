"""Integration tests: save_snapshot publishes immutable versioned snapshots (B1).

These drive the real ``FilesystemManager.save_snapshot`` writer path (not just
the SnapshotVersionStore unit) and prove:

  1. The public ``<base>/<agent_id>`` path becomes a symlink to an immutable
     version directory, with content intact.
  2. Re-saving advances the version and GCs the unreferenced old one.
  3. The original B1 race is gone: while a reader copies the current version,
     a concurrent re-save (republish) does NOT delete/mutate the source the
     reader holds -- no FileNotFoundError, complete copy.
"""

from __future__ import annotations

import shutil
import threading
import types
from pathlib import Path

import pytest

from massgen.filesystem_manager._filesystem_manager import FilesystemManager
from massgen.filesystem_manager._snapshot_version_store import SnapshotVersionStore
from massgen.orchestrator_collaborators.snapshot_manager import SnapshotManager
from massgen.orchestrator_collaborators.workspace_lifecycle_manager import (
    WorkspaceLifecycleManager,
)


@pytest.fixture(autouse=True)
def _reset_store():
    SnapshotVersionStore.reset_all_for_tests()
    yield
    SnapshotVersionStore.reset_all_for_tests()


def _make_writer_fm(base: Path, agent_id: str, workspace: Path) -> FilesystemManager:
    fm = FilesystemManager.__new__(FilesystemManager)
    fm.agent_id = agent_id
    fm.use_two_tier_workspace = False
    fm.cwd = str(workspace)
    fm.snapshot_storage = base / agent_id
    fm.snapshot_storage.mkdir(parents=True, exist_ok=True)
    return fm


def _seed_workspace(ws: Path, marker: str, n_files: int = 1) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    for i in range(n_files):
        (ws / f"file{i}.txt").write_text(f"{marker}-{i}")
    sub = ws / "src"
    sub.mkdir(exist_ok=True)
    (sub / "main.py").write_text(f"# {marker}\n")


@pytest.mark.asyncio
async def test_save_snapshot_publishes_symlinked_version(tmp_path) -> None:
    base = tmp_path / "snapshot_storage"
    ws = tmp_path / "ws_b"
    _seed_workspace(ws, "round1")
    fm = _make_writer_fm(base, "agentB", ws)

    await fm.save_snapshot()

    link = base / "agentB"
    assert link.is_symlink(), "snapshot_storage/<agent_id> must be a symlink to an immutable version"
    assert (link / "file0.txt").read_text() == "round1-0"
    assert (link / "src" / "main.py").exists()
    # The concrete version lives under .versions
    target = link.resolve()
    assert target.parent == base / ".versions" / "agentB"
    assert target.name == "v1"


@pytest.mark.asyncio
async def test_resave_advances_version_and_gcs_old(tmp_path) -> None:
    base = tmp_path / "snapshot_storage"
    ws = tmp_path / "ws_b"
    _seed_workspace(ws, "round1")
    fm = _make_writer_fm(base, "agentB", ws)

    await fm.save_snapshot()
    v1 = (base / "agentB").resolve()

    # New workspace content, save again.
    shutil.rmtree(ws)
    _seed_workspace(ws, "round2")
    await fm.save_snapshot()

    link = base / "agentB"
    v2 = link.resolve()
    assert (link / "file0.txt").read_text() == "round2-0"
    assert v2.name == "v2"
    assert not v1.exists(), "unreferenced previous version should be GC'd"


@pytest.mark.asyncio
async def test_resave_during_read_does_not_corrupt(tmp_path) -> None:
    """The original B1 race: re-save while a peer copies the current version."""
    base = tmp_path / "snapshot_storage"
    ws = tmp_path / "ws_b"
    _seed_workspace(ws, "round1", n_files=40)
    fm = _make_writer_fm(base, "agentB", ws)
    await fm.save_snapshot()

    store = SnapshotVersionStore.for_base(base)

    errors: list[Exception] = []
    copied_ok: list[bool] = []
    reader_started = threading.Event()

    def _reader():
        pinned = store.acquire("agentB")
        reader_started.set()
        try:
            for i in range(15):
                dest = tmp_path / f"copy_{i}"
                shutil.copytree(pinned, dest)
                # src/main.py + 40 files == 41 entries
                assert (dest / "file0.txt").read_text() == "round1-0"
                assert len(list(dest.iterdir())) == 41
                shutil.rmtree(dest)
            copied_ok.append(True)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
        finally:
            store.release(pinned)

    t = threading.Thread(target=_reader)
    t.start()
    reader_started.wait(timeout=5)

    # Concurrently republish (writer) many times while the reader copies.
    for r in range(2, 25):
        shutil.rmtree(ws)
        _seed_workspace(ws, f"round{r}", n_files=40)
        await fm.save_snapshot()

    t.join(timeout=15)

    assert not errors, f"reader saw corruption during concurrent re-save (B1 regression): {errors}"
    assert copied_ok == [True]


def _make_orch_stub():
    """Minimal orchestrator stub exposing the helpers the interrupted/copy paths use."""
    orch = types.SimpleNamespace()
    orch._has_meaningful_workspace_content = lambda p: bool(p) and Path(p).exists() and any(Path(p).iterdir())
    orch._copy_workspace_contents = lambda src, dest, replace_destination=False: WorkspaceLifecycleManager.copy_workspace_contents(
        Path(src),
        Path(dest),
        replace_destination=replace_destination,
    )
    return orch


@pytest.mark.asyncio
async def test_interrupted_save_over_published_symlink_does_not_crash(tmp_path) -> None:
    """Regression: interrupted-turn save must not rmtree the published symlink.

    When an empty/metadata-only version was already published (public path is a
    symlink) and the live workspace has content, the interrupted-turn save used
    to do shutil.rmtree(<symlink>) -> OSError -> the snapshot was silently lost.
    It must instead publish a new version.
    """
    base = tmp_path / "snapshot_storage"
    base.mkdir()
    ws = tmp_path / "ws_b"

    # Publish an EMPTY version first so the public path becomes a symlink with no content.
    store = SnapshotVersionStore.for_base(base)
    store.publish_version("agentB", lambda d: None)
    link = base / "agentB"
    assert link.is_symlink()
    assert not any(link.iterdir())

    # Now the live workspace has real content.
    _seed_workspace(ws, "interrupted")

    fm = FilesystemManager.__new__(FilesystemManager)
    fm.agent_id = "agentB"
    fm.snapshot_storage = link
    fm.get_current_workspace = lambda: str(ws)
    backend = types.SimpleNamespace(filesystem_manager=fm)

    sm = SnapshotManager(_make_orch_stub())

    # Must not raise (old code raised OSError on rmtree of the symlink).
    sm.save_partial_workspace_snapshots_for_interrupted_turn(
        agent_id="agentB",
        backend=backend,
        timestamp="t0",
        log_session_dir=None,
    )

    # A new version was published with the workspace content; symlink still valid.
    assert link.is_symlink()
    assert (link / "file0.txt").read_text() == "interrupted-0"


@pytest.mark.asyncio
async def test_orchestrator_reader_pins_version(tmp_path, monkeypatch) -> None:
    """End-to-end wiring: copy_all_snapshots_to_temp_workspace must acquire() a
    pinned concrete version (not read the raw symlink). If the acquire() call were
    removed from snapshot_manager, this test fails.
    """
    base = tmp_path / "snapshot_storage"
    base.mkdir()

    # Publish a snapshot for the source agent B.
    ws_b = tmp_path / "ws_b"
    _seed_workspace(ws_b, "peerwork")
    writer = _make_writer_fm(base, "agentB", ws_b)
    await writer.save_snapshot()

    store = SnapshotVersionStore.for_base(base)

    # Spy on acquire/release through the real store.
    acquired_names: list[str] = []
    real_acquire = store.acquire
    real_release = store.release
    released: list = []
    monkeypatch.setattr(store, "acquire", lambda name: (acquired_names.append(name), real_acquire(name))[1])
    monkeypatch.setattr(store, "release", lambda v: (released.append(v), real_release(v))[1])

    # Viewing agent A with a real temp workspace + the real copy method.
    viewer_fm = FilesystemManager.__new__(FilesystemManager)
    viewer_fm.agent_temporary_workspace = tmp_path / "temp_ws_a"
    monkeypatch.setattr(viewer_fm, "_normalize_media_call_ledger_paths", lambda **kw: None)
    viewer_fm.cwd = str(tmp_path / "ws_a")

    viewer_agent = types.SimpleNamespace(backend=types.SimpleNamespace(filesystem_manager=viewer_fm))
    source_agent = types.SimpleNamespace(backend=types.SimpleNamespace(filesystem_manager=writer))

    orch = types.SimpleNamespace()
    orch._snapshot_storage = str(base)
    orch.agents = {"agentA": viewer_agent, "agentB": source_agent}
    orch.coordination_tracker = types.SimpleNamespace(get_reverse_agent_mapping=lambda: {})
    orch._step_mode = None
    orch._step_inputs = None

    sm = SnapshotManager(orch)
    result = await sm.copy_all_snapshots_to_temp_workspace("agentA")

    # acquire() was actually used for the source agent (the load-bearing wiring).
    assert "agentB" in acquired_names, "reader did not acquire() a pinned version"
    # The copy produced agentB's peer content.
    assert result is not None
    assert (Path(result) / "agentB" / "file0.txt").read_text() == "peerwork-0"
    # Pins were released (no refcount leak that would disable GC).
    assert store._refcounts == {}, f"refcount leak after copy: {store._refcounts}"
