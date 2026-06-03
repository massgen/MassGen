#!/usr/bin/env python3
"""Event streaming, timeline recording, and coordination-UI construction.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import sys
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass


from ..frontend.coordination_ui import CoordinationUI


def _setup_event_streaming() -> None:
    """Configure event streaming to stdout for subprocess-based TUI display.

    When --stream-events is passed, this adds a listener to the EventEmitter
    that writes all events as JSON lines to stdout. This enables parent processes
    (like the TUI subagent modal) to receive real-time updates by reading stdout.

    Events are written in JSONL format (one JSON object per line), flushed
    immediately for real-time streaming.
    """
    from . import env

    env._stream_events_active = True

    from ..events import get_event_emitter

    def stream_to_stdout(event):
        """Write event as JSON line to stdout."""
        sys.stdout.write(event.to_json() + "\n")
        sys.stdout.flush()

    # Get the event emitter (initialized by setup_logging)
    emitter = get_event_emitter()
    if emitter:
        emitter.add_listener(stream_to_stdout)


def _setup_timeline_event_recording() -> None:
    """Emit timeline_entry events derived from streaming events (env-gated)."""
    import os

    if not os.environ.get("MASSGEN_TUI_TIMELINE_EVENTS"):
        return

    from ..events import get_event_emitter
    from ..frontend.displays.timeline_event_recorder import TimelineEventRecorder

    emitter = get_event_emitter()
    if not emitter:
        return

    def emit_line(line: str) -> None:
        emitter.emit_raw("timeline_entry", line=line)

    recorder = TimelineEventRecorder(emit_line)

    def record_event(event):
        try:
            recorder.handle_event(event)
        except Exception:
            pass

    emitter.add_listener(record_event)

    try:
        import atexit

        atexit.register(recorder.flush)
    except Exception:
        pass


def _build_coordination_ui(ui_config: dict[str, Any]) -> CoordinationUI:
    """Create a CoordinationUI with display_kwargs passthrough (incl. theme)."""
    display_kwargs = dict(ui_config.get("display_kwargs", {}) or {})
    theme = ui_config.get("theme")
    if theme is not None and "theme" not in display_kwargs:
        display_kwargs["theme"] = theme
    if ui_config.get("automation_mode"):
        display_kwargs["automation_mode"] = True
    if ui_config.get("skip_agent_selector"):
        display_kwargs["skip_agent_selector"] = True

    return CoordinationUI(
        display_type=ui_config.get("display_type", "textual_terminal"),
        logging_enabled=ui_config.get("logging_enabled", True),
        enable_final_presentation=True,  # Ensures final presentation is generated/saved
        **display_kwargs,
    )
