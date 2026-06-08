"""Deterministic tests for the live-test non-blocking stdout helper.

These pin the contract the live steering/interrupt-resume tests rely on: a
non-blocking read must return "" (not block) when no line is available yet, so
the caller's ``while time.time() < deadline`` guard always gets to re-check.
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

from massgen.tests._live_proc_io import read_line_nonblocking, set_nonblocking


def _pipe_streams():
    r_fd, w_fd = os.pipe()
    r = os.fdopen(r_fd, "r")
    w = os.fdopen(w_fd, "w")
    return r, w


def test_returns_empty_when_no_data_yet_does_not_block():
    r, w = _pipe_streams()
    try:
        set_nonblocking(r)
        start = time.time()
        # Nothing written yet — must return "" immediately, not block.
        assert read_line_nonblocking(r) == ""
        assert time.time() - start < 1.0
    finally:
        r.close()
        w.close()


def test_returns_line_when_available():
    r, w = _pipe_streams()
    try:
        set_nonblocking(r)
        w.write("LOG_DIR: /tmp/run\n")
        w.flush()
        assert read_line_nonblocking(r) == "LOG_DIR: /tmp/run\n"
    finally:
        r.close()
        w.close()


def test_returns_empty_at_eof():
    r, w = _pipe_streams()
    set_nonblocking(r)
    w.close()  # writer gone → EOF
    try:
        assert read_line_nonblocking(r) == ""
    finally:
        r.close()


def test_none_stream_is_safe():
    assert read_line_nonblocking(None) == ""
    set_nonblocking(None)  # no raise


def test_set_nonblocking_tolerates_no_fileno():
    # A stand-in without a real fd (e.g. a stub) must not raise.
    set_nonblocking(SimpleNamespace(fileno=lambda: (_ for _ in ()).throw(ValueError())))
