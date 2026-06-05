"""Immutable, versioned snapshot publishing for agent snapshot storage.

Background (B1 race)
--------------------
Agent snapshots live at ``<base>/<agent_id>``. Historically ``save_snapshot``
rewrote that directory *in place* (``rmtree`` + rebuild), and the peer-context
copy (``copy_snapshots_to_temp_workspace``) read the very same directory. Once
the copy was offloaded to a worker thread (``asyncio.to_thread``), the implicit
single-threaded serialization between writer and reader was lost: agent A's copy
thread could ``copytree`` ``<base>/B`` while agent B's ``save_snapshot`` deleted
and rebuilt it on the event loop, yielding ``FileNotFoundError`` or a torn copy.

Fix
---
Writes publish a brand-new **immutable** version directory under
``<base>/.versions/<agent_id>/v<N>`` and then atomically repoint the public
path ``<base>/<agent_id>`` (now a symlink) at it. A published version is never
mutated or deleted while a reader may still be using it:

* Readers ``acquire`` the *current* version under a lock, which resolves the
  symlink to a concrete ``v<N>`` directory and increments a refcount. They copy
  from that concrete directory (immune to any subsequent republish) and
  ``release`` it when done.
* ``publish_version`` repoints the symlink and runs GC *under the same lock*, so
  a reader either sees the old version (and pins it, preventing GC) or the new
  one — never a half-deleted directory. GC skips any version with a non-zero
  refcount.

The public ``<base>/<agent_id>`` path remains a normal-looking directory to every
other reader (symlinks are transparent), so the on-disk layout consumers depend
on is unchanged.

Platform note: if symlinks are unavailable (e.g. unprivileged Windows), the
store falls back to copying content directly into ``<base>/<agent_id>`` — losing
the race protection but preserving functionality.
"""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from massgen.logger_config import logger

_VERSIONS_DIRNAME = ".versions"


def _safe_rmtree(path: Path) -> None:
    try:
        if path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"[SnapshotVersionStore] rmtree failed for {path}: {e}")


class SnapshotVersionStore:
    """Per-base registry coordinating immutable snapshot versions.

    One instance exists per snapshot-storage *base* path (shared across all
    agents' ``FilesystemManager``s and the orchestrator's ``SnapshotManager``,
    which both reach it via :meth:`for_base`).
    """

    _instances: dict[str, SnapshotVersionStore] = {}
    _instances_lock = threading.Lock()

    def __init__(self, base: Path) -> None:
        self._base = Path(base)
        self._versions_root = self._base / _VERSIONS_DIRNAME
        self._lock = threading.RLock()
        self._refcounts: dict[str, int] = {}
        self._next_version: dict[str, int] = {}
        # Versions reserved by an in-flight publish but not yet published. GC must
        # never delete these: a concurrent publisher for the same name may be
        # mid-``populate`` (which runs outside the lock), and that version has no
        # refcount yet because no reader can acquire an unpublished version.
        self._inflight: set[str] = set()

    # -- instance lookup ------------------------------------------------------
    @classmethod
    def for_base(cls, base: os.PathLike | str) -> SnapshotVersionStore:
        key = str(Path(base))
        with cls._instances_lock:
            inst = cls._instances.get(key)
            if inst is None:
                inst = cls(Path(base))
                cls._instances[key] = inst
            return inst

    @classmethod
    def reset_all_for_tests(cls) -> None:
        with cls._instances_lock:
            cls._instances.clear()

    # -- paths ----------------------------------------------------------------
    def _agent_versions_dir(self, agent_id: str) -> Path:
        return self._versions_root / agent_id

    def _link_path(self, agent_id: str) -> Path:
        return self._base / agent_id

    # -- publish --------------------------------------------------------------
    def _reserve_next_version(self, agent_id: str, vroot: Path) -> int:
        """Reserve the next version number for ``agent_id`` (lock held)."""
        n = self._next_version.get(agent_id)
        if n is None:
            existing = 0
            if vroot.exists():
                for child in vroot.iterdir():
                    name = child.name
                    if child.is_dir() and name.startswith("v") and name[1:].isdigit():
                        existing = max(existing, int(name[1:]))
            n = existing + 1
        self._next_version[agent_id] = n + 1
        return n

    def publish_version(self, agent_id: str, populate: Callable[[Path], None]) -> Path | None:
        """Build a new immutable version, then atomically publish + GC.

        ``populate(version_dir)`` must fully write the snapshot content into the
        (empty) ``version_dir`` it is given. It runs *outside* the lock since it
        is the slow, blocking work; the version directory is freshly reserved and
        not yet referenced by anything, so building it is race-free.
        """
        vroot = self._agent_versions_dir(agent_id)
        vroot.mkdir(parents=True, exist_ok=True)

        with self._lock:
            n = self._reserve_next_version(agent_id, vroot)
            version_dir = vroot / f"v{n}"
            version_key = str(Path(os.path.realpath(version_dir)))
            # Mark in-flight so a concurrent same-name publish's GC won't delete
            # this directory while we populate it outside the lock.
            self._inflight.add(version_key)

        try:
            # Build content outside the lock (slow, but the dir is private/unreferenced).
            if version_dir.exists():
                _safe_rmtree(version_dir)
            version_dir.mkdir(parents=True, exist_ok=True)
            populate(version_dir)

            # Publish + GC atomically w.r.t. acquire().
            with self._lock:
                self._repoint_symlink(agent_id, version_dir)
                self._inflight.discard(version_key)
                self._gc(agent_id, keep=version_dir)
        except Exception:
            with self._lock:
                self._inflight.discard(version_key)
            raise
        return version_dir

    def _repoint_symlink(self, agent_id: str, version_dir: Path) -> None:
        link = self._link_path(agent_id)
        target = os.path.relpath(version_dir, self._base)
        tmp = self._base / f".{agent_id}.lnk.{uuid.uuid4().hex}"
        try:
            os.symlink(target, tmp)
        except OSError as e:
            # No symlink support: fall back to a direct (unprotected) copy.
            logger.warning(
                f"[SnapshotVersionStore] symlink unsupported ({e}); falling back to direct copy " f"for {link} (snapshot race protection disabled on this platform)",
            )
            _safe_rmtree(link)
            shutil.copytree(version_dir, link, symlinks=True, ignore_dangling_symlinks=True)
            return

        # os.replace cannot atomically replace a non-empty real directory; if the
        # public path is a legacy real dir (first publish), remove it first. No
        # reader can be mid-copy of it because no version had been published yet.
        if link.exists() and not link.is_symlink() and link.is_dir():
            _safe_rmtree(link)
        try:
            os.replace(tmp, link)
        except OSError as e:  # pragma: no cover - defensive
            logger.error(f"[SnapshotVersionStore] failed to repoint symlink {link}: {e}")
            tmp.unlink(missing_ok=True)

    # -- acquire / release ----------------------------------------------------
    def acquire(self, agent_id: str) -> Path | None:
        """Pin and return the concrete current version dir for ``agent_id``.

        Returns ``None`` if no snapshot exists yet. The returned directory will
        not be GC'd until a matching :meth:`release`. Resolution + refcount are
        atomic w.r.t. :meth:`publish_version`'s repoint+GC.
        """
        with self._lock:
            link = self._link_path(agent_id)
            if not link.exists():  # follows symlink; dangling -> False
                return None
            concrete = Path(os.path.realpath(link))
            key = str(concrete)
            self._refcounts[key] = self._refcounts.get(key, 0) + 1
            return concrete

    def release(self, version_dir: Path | None) -> None:
        if version_dir is None:
            return
        with self._lock:
            key = str(Path(version_dir))
            count = self._refcounts.get(key, 0)
            if count <= 1:
                self._refcounts.pop(key, None)
            else:
                self._refcounts[key] = count - 1

    # -- gc -------------------------------------------------------------------
    def _gc(self, agent_id: str, keep: Path) -> None:
        vroot = self._agent_versions_dir(agent_id)
        if not vroot.exists():
            return
        keep_key = str(Path(os.path.realpath(keep)))
        for child in vroot.iterdir():
            if not child.is_dir():
                continue
            child_key = str(Path(os.path.realpath(child)))
            if child_key == keep_key:
                continue
            if child_key in self._inflight:
                continue
            if self._refcounts.get(child_key, 0) > 0:
                continue
            _safe_rmtree(child)
