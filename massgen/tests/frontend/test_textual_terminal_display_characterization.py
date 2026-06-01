"""Characterization safety net for ``textual_terminal_display`` BEFORE collaborator extraction.

This file pins the CURRENT observable behavior of
``massgen/frontend/displays/textual_terminal_display.py`` so the planned
collaborator extractions (TerminalCapabilityProbe, ProviderModelResolver,
WidgetTreeDebugDumper + TuiTimingWatchdog, ...) can be proven to introduce no
breaking changes.

Scope (matches the refactor plan's lowest-risk first steps):
  1. Public-contract import + signature stability for the six exported names
     plus the re-exported module constants.
  2. ``TextualTerminalDisplay`` construction/initialization with realistic config.
  3. The exact seams the FIRST ~3 extraction steps cross:
       - Step 1: TerminalCapabilityProbe -- ``_detect_emoji_support``,
         ``_detect_terminal_type``, ``_get_adaptive_refresh_rate``, ``_get_icon``
         + the ``EMOJI_FALLBACKS`` constant.
       - Step 3: TuiTimingWatchdog -- ``_start_stall_watchdog`` /
         ``_stop_stall_watchdog`` / ``_heartbeat_tick`` lifecycle (debug-gated),
         and ``_dump_widget_sizes`` contract presence.

These tests MUST pass against the current unmodified code. They are written to
fail loudly if the observable behavior changes during refactoring.

Note on ``_dump_widget_sizes`` (step 3): its full behavior writes a widget-tree
JSON dump from a *mounted* Textual app (uses ``self.query`` / ``self.children``).
Exercising that requires a Textual pilot harness; here we pin only its contract
presence/binding so the extraction's thin delegator can be checked. The
JSON-dump side effect is intentionally left to the dedicated pilot/snapshot
suite -- writing a "dump produces JSON" test without a real DOM would be a
test-that-always-passes, which the TDD contract forbids.
"""

from __future__ import annotations

import inspect
import threading

import pytest

from massgen.frontend.displays import textual_terminal_display as ttd

# These tests run as plain sync frontend tests (matching the style of
# test_mode_bar_layout.py / test_subagent_screen_wiring.py -- no module-level
# marker). TextualTerminalDisplay is a plain TerminalDisplay subclass and
# constructs without a running Textual app; the watchdog tests build TextualApp
# via __new__ and set only the attributes the methods touch.


# ---------------------------------------------------------------------------
# (1) Public-contract: every exported name imports cleanly with stable shape.
# ---------------------------------------------------------------------------

PUBLIC_NAMES = (
    "TextualApp",
    "AgentPanel",
    "TextualTerminalDisplay",
    "ProgressIndicator",
    "tui_log",
    "_PrecollabSubagentState",
)

# Re-exported module constants that the facade must keep importable after the
# capabilities / content-filter extractions (steps 1 and 14).
REEXPORTED_CONSTANTS = (
    "EMOJI_FALLBACKS",
    "CRITICAL_PATTERNS",
    "CRITICAL_CONTENT_TYPES",
)


def test_public_contract_names_import_cleanly():
    """All six public names are importable from the facade module."""
    from massgen.frontend.displays.textual_terminal_display import (  # noqa: F401
        AgentPanel,
        ProgressIndicator,
        TextualApp,
        TextualTerminalDisplay,
        _PrecollabSubagentState,
        tui_log,
    )

    for name in PUBLIC_NAMES:
        assert hasattr(ttd, name), f"missing public name: {name}"


def test_reexported_constants_remain_importable():
    """EMOJI_FALLBACKS / CRITICAL_PATTERNS / CRITICAL_CONTENT_TYPES stay on the facade."""
    from massgen.frontend.displays.textual_terminal_display import (  # noqa: F401
        CRITICAL_CONTENT_TYPES,
        CRITICAL_PATTERNS,
        EMOJI_FALLBACKS,
    )

    for name in REEXPORTED_CONSTANTS:
        assert hasattr(ttd, name), f"missing re-exported constant: {name}"


def test_tui_log_is_callable():
    """tui_log is a re-exported callable (sourced from shared.tui_debug)."""
    assert callable(ttd.tui_log)


def test_public_signatures_are_stable():
    """Pin constructor signatures of the public classes (delegators must match)."""
    assert str(inspect.signature(ttd.TextualTerminalDisplay.__init__)) == "(self, agent_ids: list[str], **kwargs: Any)"
    assert str(inspect.signature(ttd.ProgressIndicator.__init__)) == ("(self, message: str = 'Loading...', spinner_type: str = 'unicode', " "show_progress: bool = False, **kwargs)")
    assert str(inspect.signature(ttd._PrecollabSubagentState.__init__)) == "(self) -> None"


def test_precollab_subagent_state_slots_and_defaults():
    """_PrecollabSubagentState pins its __slots__ and default field values."""
    state = ttd._PrecollabSubagentState()
    assert ttd._PrecollabSubagentState.__slots__ == (
        "call_id",
        "agent_id",
        "data",
        "status_callback",
        "auto_opened",
    )
    assert state.call_id is None
    assert state.agent_id is None
    assert state.data is None
    assert state.status_callback is None
    assert state.auto_opened is False


def test_emoji_fallbacks_known_entries():
    """EMOJI_FALLBACKS pins the ASCII fallback mapping used by _get_icon."""
    assert ttd.EMOJI_FALLBACKS["🚀"] == ">>"
    assert ttd.EMOJI_FALLBACKS["✅"] == "[✓]"
    assert ttd.EMOJI_FALLBACKS["❌"] == "[X]"
    assert ttd.EMOJI_FALLBACKS["🤖"] == "[A]"


def test_critical_content_types_pinned():
    """CRITICAL_CONTENT_TYPES pins the set of immediately-flushed content types."""
    assert ttd.CRITICAL_CONTENT_TYPES == {"status", "presentation", "tool", "vote", "error"}


# ---------------------------------------------------------------------------
# (2) Construction / initialization with realistic config.
# ---------------------------------------------------------------------------

REALISTIC_KWARGS = dict(
    theme="dark",
    max_line_length=80,
    max_web_search_lines=4,
    show_timestamps=False,
    refresh_rate=8,
    default_coordination_mode="parallel",
    default_plan_mode="normal",
    enable_syntax_highlighting=True,
)


def _make_display(monkeypatch, **overrides):
    """Build a TextualTerminalDisplay in a deterministic environment.

    Clears emoji/terminal env signals so capability detection is reproducible
    unless a test deliberately sets them.
    """
    for var in ("TERM_PROGRAM", "WT_SESSION", "WT_PROFILE_ID", "SSH_CONNECTION", "SSH_CLIENT", "LANG"):
        monkeypatch.delenv(var, raising=False)
    kwargs = dict(REALISTIC_KWARGS)
    kwargs.update(overrides)
    return ttd.TextualTerminalDisplay(["agent1", "agent2"], **kwargs)


def test_construction_with_realistic_config(monkeypatch):
    """A realistic config constructs and caches config-derived fields."""
    display = _make_display(monkeypatch)

    assert display.agent_ids == ["agent1", "agent2"]
    assert display.theme == "dark"
    assert display.max_line_length == 80
    assert display.show_timestamps is False
    # explicit refresh_rate is coerced to int and preserved
    assert display.refresh_rate == 8
    # per-agent buffers are seeded for each agent id
    assert set(display._buffers.keys()) == {"agent1", "agent2"}
    # file-output fields start empty (writer setup happens in initialize())
    assert display.agent_files == {}
    assert display.system_status_file is None
    # capability fields are cached on the instance (the step-1 seam outputs)
    assert isinstance(display.emoji_support, bool)
    assert isinstance(display._terminal_type, str)


def test_explicit_refresh_rate_overrides_adaptive(monkeypatch):
    """An explicitly-provided refresh_rate is not replaced by adaptive detection."""
    display = _make_display(monkeypatch, refresh_rate=15)
    assert display.refresh_rate == 15


def test_adaptive_refresh_rate_used_when_unset(monkeypatch):
    """When refresh_rate is None, the adaptive value for the detected terminal is used."""
    display = _make_display(monkeypatch, refresh_rate=None)
    # unknown terminal -> adaptive default of 6 (pinned in _get_adaptive_refresh_rate)
    assert display.refresh_rate == display._get_adaptive_refresh_rate(display._terminal_type)


# ---------------------------------------------------------------------------
# (3a) Step-1 seam: TerminalCapabilityProbe methods.
# These must produce identical outputs for known environments after extraction.
# ---------------------------------------------------------------------------


@pytest.fixture()
def probe_display(monkeypatch):
    """A display whose env we control per-test for capability detection."""
    return _make_display(monkeypatch)


@pytest.mark.parametrize(
    "env,expected",
    [
        ({"TERM_PROGRAM": "vscode"}, True),
        ({"TERM_PROGRAM": "iTerm.app"}, True),
        ({"TERM_PROGRAM": "Apple_Terminal"}, True),
        ({"WT_SESSION": "abc"}, True),
        ({"WT_PROFILE_ID": "xyz"}, True),
        ({"LANG": "en_US.UTF-8"}, True),
    ],
)
def test_detect_emoji_support_positive_envs(monkeypatch, probe_display, env, expected):
    """Known emoji-capable environments report emoji support."""
    for var in ("TERM_PROGRAM", "WT_SESSION", "WT_PROFILE_ID", "LANG"):
        monkeypatch.delenv(var, raising=False)
    # Force a non-UTF-8 preferred encoding so only the env signal decides.
    monkeypatch.setattr("locale.getpreferredencoding", lambda *a, **k: "ascii")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert probe_display._detect_emoji_support() is expected


def test_detect_emoji_support_utf8_locale(monkeypatch, probe_display):
    """A UTF-8 preferred encoding alone enables emoji support."""
    for var in ("TERM_PROGRAM", "WT_SESSION", "WT_PROFILE_ID", "LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("locale.getpreferredencoding", lambda *a, **k: "UTF-8")
    assert probe_display._detect_emoji_support() is True


def test_detect_emoji_support_negative_env(monkeypatch, probe_display):
    """With no emoji signals and a non-UTF-8 locale, emoji support is False."""
    for var in ("TERM_PROGRAM", "WT_SESSION", "WT_PROFILE_ID", "LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("locale.getpreferredencoding", lambda *a, **k: "ascii")
    assert probe_display._detect_emoji_support() is False


@pytest.mark.parametrize(
    "env,expected",
    [
        ({"TERM_PROGRAM": "vscode"}, "vscode"),
        ({"TERM_PROGRAM": "iTerm.app"}, "iterm"),
        ({"SSH_CONNECTION": "1.2.3.4 22 5.6.7.8 22"}, "ssh"),
        ({"SSH_CLIENT": "1.2.3.4 22 22"}, "ssh"),
        ({"WT_SESSION": "abc"}, "windows_terminal"),
        ({}, "unknown"),
    ],
)
def test_detect_terminal_type(monkeypatch, probe_display, env, expected):
    """Terminal-type detection maps env signals to the pinned type strings."""
    for var in ("TERM_PROGRAM", "SSH_CONNECTION", "SSH_CLIENT", "WT_SESSION"):
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert probe_display._detect_terminal_type() == expected


@pytest.mark.parametrize(
    "terminal_type,expected_rate",
    [
        ("ssh", 4),
        ("vscode", 4),
        ("iterm", 10),
        ("windows_terminal", 4),
        ("unknown", 6),
        ("some_unmapped_type", 6),
    ],
)
def test_get_adaptive_refresh_rate(probe_display, terminal_type, expected_rate):
    """Adaptive refresh-rate table is pinned per terminal type."""
    assert probe_display._get_adaptive_refresh_rate(terminal_type) == expected_rate


def test_get_icon_returns_emoji_when_supported(probe_display):
    """_get_icon returns the original emoji when emoji_support is True."""
    probe_display.emoji_support = True
    assert probe_display._get_icon("🚀") == "🚀"


def test_get_icon_returns_fallback_when_unsupported(probe_display):
    """_get_icon returns the EMOJI_FALLBACKS entry when emoji_support is False."""
    probe_display.emoji_support = False
    assert probe_display._get_icon("🚀") == ttd.EMOJI_FALLBACKS["🚀"]
    assert probe_display._get_icon("✅") == ttd.EMOJI_FALLBACKS["✅"]


def test_get_icon_passthrough_for_unknown_glyph(probe_display):
    """Unknown glyphs pass through unchanged even without emoji support."""
    probe_display.emoji_support = False
    assert probe_display._get_icon("🐉") == "🐉"


# ---------------------------------------------------------------------------
# (3b) Step-3 seam: TuiTimingWatchdog lifecycle + heartbeat + dump contract.
# These methods live on TextualApp; we build it via __new__ and set only the
# attributes the watchdog logic touches (matching test_subagent_screen_wiring's
# __new__ pattern). No Textual app needs to be mounted.
# ---------------------------------------------------------------------------


def _make_watchdog_app(*, timing_debug: bool):
    """TextualApp shell with just the watchdog/heartbeat attributes initialized."""
    app = ttd.TextualApp.__new__(ttd.TextualApp)
    app._timing_debug = timing_debug
    app._stall_watchdog_thread = None
    app._stall_watchdog_stop = threading.Event()
    app._stall_watchdog_threshold_s = 0.8
    app._last_heartbeat_at = None
    app._last_stall_dump_at = 0.0
    app._thread_id = threading.get_ident()
    app._event_batch = []
    app._pending_flush = False
    return app


def test_stall_watchdog_start_stop_lifecycle_when_enabled():
    """With timing debug on, start launches a daemon thread and stop joins it."""
    app = _make_watchdog_app(timing_debug=True)
    try:
        app._start_stall_watchdog()
        thread = app._stall_watchdog_thread
        assert thread is not None
        assert thread.is_alive()
        assert thread.daemon is True
        assert thread.name == "massgen-tui-stall-watchdog"
    finally:
        app._stop_stall_watchdog()
    # stop clears the handle and joins the thread
    assert app._stall_watchdog_thread is None


def test_stall_watchdog_start_is_noop_when_disabled():
    """With timing debug off, start spawns no watchdog thread."""
    app = _make_watchdog_app(timing_debug=False)
    app._start_stall_watchdog()
    assert app._stall_watchdog_thread is None


def test_stall_watchdog_start_is_idempotent_while_alive():
    """A second start does not replace a still-running watchdog thread."""
    app = _make_watchdog_app(timing_debug=True)
    try:
        app._start_stall_watchdog()
        first = app._stall_watchdog_thread
        app._start_stall_watchdog()
        assert app._stall_watchdog_thread is first
    finally:
        app._stop_stall_watchdog()


def test_stop_watchdog_safe_when_never_started():
    """Stopping a never-started watchdog is a safe no-op."""
    app = _make_watchdog_app(timing_debug=True)
    app._stop_stall_watchdog()  # must not raise
    assert app._stall_watchdog_thread is None


def test_heartbeat_tick_records_and_updates_timestamp():
    """_heartbeat_tick always records a monotonic timestamp (debug off path)."""
    app = _make_watchdog_app(timing_debug=False)
    assert app._last_heartbeat_at is None
    app._heartbeat_tick()
    first = app._last_heartbeat_at
    assert first is not None
    app._heartbeat_tick()
    assert app._last_heartbeat_at >= first


def test_heartbeat_tick_with_debug_does_not_raise():
    """_heartbeat_tick under timing debug exercises the stall-log path safely."""
    app = _make_watchdog_app(timing_debug=True)
    # Seed an old heartbeat so the delta exceeds the 0.25s lag threshold.
    app._last_heartbeat_at = 0.0
    app._heartbeat_tick()  # must not raise; logging path tolerates missing batch
    assert app._last_heartbeat_at is not None


def test_dump_widget_sizes_contract_present():
    """_dump_widget_sizes remains a bound method on TextualApp (D-key delegator).

    Full behavior (writing widget_sizes.json from a mounted DOM) requires a
    Textual pilot harness and is covered by the dedicated pilot/snapshot suite;
    here we pin only the contract so the extraction's thin delegator is checked.
    """
    assert callable(getattr(ttd.TextualApp, "_dump_widget_sizes", None))
    sig = inspect.signature(ttd.TextualApp._dump_widget_sizes)
    assert list(sig.parameters) == ["self"]
