"""Unit tests for SnapshotVersionStore (B1 immutable-versioned snapshots).

The store guarantees that a reader copying agent B's snapshot reads from an
immutable version directory that B's concurrent ``save_snapshot`` (republish)
will never delete or mutate underneath it.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from massgen.filesystem_manager._snapshot_version_store import SnapshotVersionStore


@pytest.fixture(autouse=True)
def _reset_store():
    SnapshotVersionStore.reset_all_for_tests()
    yield
    SnapshotVersionStore.reset_all_for_tests()


def _populate(content: dict[str, str]):
    def _fn(dest: Path) -> None:
        for name, text in content.items():
            (dest / name).write_text(text)

    return _fn


def test_publish_creates_version_and_symlink(tmp_path):
    store = SnapshotVersionStore.for_base(tmp_path)
    v1 = store.publish_version("agentA", _populate({"answer.md": "v1"}))

    link = tmp_path / "agentA"
    assert link.is_symlink(), "public path must be a symlink to the version"
    assert (link / "answer.md").read_text() == "v1"
    assert v1.name == "v1"
    assert v1.parent == tmp_path / ".versions" / "agentA"


def test_republish_advances_version_and_repoints(tmp_path):
    store = SnapshotVersionStore.for_base(tmp_path)
    store.publish_version("agentA", _populate({"answer.md": "v1"}))
    v2 = store.publish_version("agentA", _populate({"answer.md": "v2"}))

    link = tmp_path / "agentA"
    assert (link / "answer.md").read_text() == "v2"
    assert Path(os.path.realpath(link)) == v2
    assert v2.name == "v2"


def test_for_base_returns_shared_instance(tmp_path):
    a = SnapshotVersionStore.for_base(tmp_path)
    b = SnapshotVersionStore.for_base(str(tmp_path))
    assert a is b, "all participants on the same base must share one store"


def test_acquire_returns_concrete_version(tmp_path):
    store = SnapshotVersionStore.for_base(tmp_path)
    v1 = store.publish_version("agentA", _populate({"answer.md": "v1"}))

    acquired = store.acquire("agentA")
    assert acquired == v1
    assert not acquired.is_symlink(), "acquire must return the concrete version dir"
    store.release(acquired)


def test_acquire_missing_agent_returns_none(tmp_path):
    store = SnapshotVersionStore.for_base(tmp_path)
    assert store.acquire("nope") is None


def test_gc_removes_unreferenced_old_versions(tmp_path):
    store = SnapshotVersionStore.for_base(tmp_path)
    v1 = store.publish_version("agentA", _populate({"answer.md": "v1"}))
    store.publish_version("agentA", _populate({"answer.md": "v2"}))
    # v1 had no readers -> GC'd when v2 published.
    assert not v1.exists(), "unreferenced previous version should be garbage-collected"


def test_acquired_version_survives_republish_and_gc(tmp_path):
    """The core race guarantee: a pinned version is never deleted by GC.

    Reader acquires v1, then TWO republishes happen. Without refcounting GC would
    delete v1 (it's neither current nor previous), corrupting the in-flight read.
    """
    store = SnapshotVersionStore.for_base(tmp_path)
    v1 = store.publish_version("agentA", _populate({"answer.md": "v1"}))

    pinned = store.acquire("agentA")
    assert pinned == v1

    store.publish_version("agentA", _populate({"answer.md": "v2"}))
    store.publish_version("agentA", _populate({"answer.md": "v3"}))

    # The pinned version is still fully intact for the reader.
    assert pinned.exists()
    assert (pinned / "answer.md").read_text() == "v1"

    # After release + another publish, it is finally collectable.
    store.release(pinned)
    store.publish_version("agentA", _populate({"answer.md": "v4"}))
    assert not pinned.exists()


def test_concurrent_publish_during_read_no_corruption(tmp_path):
    """Reproduce the B1 interleave: republish (writer) while a copy (reader) runs.

    A reader pins the current version and copies from it on a worker thread while
    the main thread republishes repeatedly. The reader's source must stay intact
    for the entire copy -- no FileNotFoundError, complete content.
    """
    import shutil

    store = SnapshotVersionStore.for_base(tmp_path)
    # Seed a version with enough files that a copy takes a measurable walk.
    store.publish_version("agentA", _populate({f"f{i}.txt": f"content-{i}" for i in range(50)}))

    errors: list[Exception] = []
    copied_ok: list[bool] = []
    start_copy = threading.Event()

    def _reader():
        pinned = store.acquire("agentA")
        start_copy.set()
        try:
            for _ in range(20):
                dest = tmp_path / f"dest_{threading.get_ident()}_{_}"
                shutil.copytree(pinned, dest)
                # Verify completeness of every copy.
                assert len(list(dest.iterdir())) == 50
                shutil.rmtree(dest)
            copied_ok.append(True)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
        finally:
            store.release(pinned)

    t = threading.Thread(target=_reader)
    t.start()
    start_copy.wait(timeout=5)
    # Hammer republishes (writer) concurrently with the reader's copies.
    for i in range(2, 40):
        store.publish_version("agentA", _populate({f"f{j}.txt": f"content-{j}-r{i}" for j in range(50)}))
    t.join(timeout=10)

    assert not errors, f"reader saw corruption/errors during concurrent republish: {errors}"
    assert copied_ok == [True]


def test_concurrent_publishers_same_name_no_inflight_gc(tmp_path):
    """A concurrent publish for the SAME name must not GC the other's in-flight version.

    Without the in-flight guard, publisher B's GC deletes publisher A's freshly
    reserved-but-unpopulated version (refcount 0, not the keep target), so A's
    populate writes into a deleted directory and crashes / produces a dangling
    symlink.
    """
    store = SnapshotVersionStore.for_base(tmp_path)
    # Seed v1 so subsequent publishes have an "old" version to tempt GC.
    store.publish_version("agentA", _populate({"answer.md": "v1"}))

    a_populating = threading.Event()
    b_done = threading.Event()
    errors: list[Exception] = []

    def _slow_populate_A(dest: Path) -> None:
        # Signal we are mid-populate, then wait until B has fully published+GC'd.
        a_populating.set()
        assert b_done.wait(timeout=5)
        (dest / "answer.md").write_text("from-A")

    def _publish_A():
        try:
            store.publish_version("agentA", _slow_populate_A)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t = threading.Thread(target=_publish_A)
    t.start()
    assert a_populating.wait(timeout=5)

    # While A is mid-populate, B publishes (repoint + GC) for the same name.
    store.publish_version("agentA", _populate({"answer.md": "from-B"}))
    b_done.set()
    t.join(timeout=10)

    assert not errors, f"concurrent publisher's in-flight version was GC'd: {errors}"
    # A's directory survived its populate and is intact.
    link = tmp_path / "agentA"
    assert link.is_symlink()
    assert (link / "answer.md").read_text() in {"from-A", "from-B"}


def test_symlink_fallback_when_unsupported(tmp_path, monkeypatch):
    """Without symlink support, publishing falls back to a direct copy that still works."""
    import massgen.filesystem_manager._snapshot_version_store as mod

    def _no_symlink(*args, **kwargs):
        raise OSError("symlinks not supported")

    monkeypatch.setattr(mod.os, "symlink", _no_symlink)

    store = SnapshotVersionStore.for_base(tmp_path)
    store.publish_version("agentA", _populate({"answer.md": "v1"}))

    link = tmp_path / "agentA"
    assert not link.is_symlink()
    assert (link / "answer.md").read_text() == "v1"
