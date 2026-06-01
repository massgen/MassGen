"""Debug helpers for the Textual terminal display.

Extracted collaborators (step 3 of the textual_terminal_display refactor):

- ``dump_widget_sizes(app)`` -- a free function that walks a mounted Textual
  app's widget tree and writes ``widget_sizes.json`` / ``timeline_debug.json``
  to the temp dir. It is the implementation behind ``TextualApp._dump_widget_sizes``
  (the D-key debug dump).
- The stall-watchdog / heartbeat helpers -- free functions operating on the
  app's own watchdog attributes (``_timing_debug``, ``_stall_watchdog_thread``,
  ``_stall_watchdog_stop``, ``_stall_watchdog_threshold_s``, ``_last_heartbeat_at``,
  ``_last_stall_dump_at``, ``_thread_id``, ``_event_batch``, ``_pending_flush``).
  ``EventBatchRouter`` remains the owner of the diagnostic batch fields; these
  helpers only read them.

These functions import nothing from Textual at module load and hold no
back-reference, so the module is import-safe even when Textual is unavailable.
The ``TextualApp`` methods stay as thin delegators that pass ``self``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import traceback

from .shared.tui_debug import tui_log

# Daemon thread name pinned by the characterization suite.
_WATCHDOG_THREAD_NAME = "massgen-tui-stall-watchdog"


def start_stall_watchdog(app) -> None:
    """Start a background watchdog to capture main-thread stack on stalls."""
    if not app._timing_debug:
        return
    if app._stall_watchdog_thread and app._stall_watchdog_thread.is_alive():
        return

    app._stall_watchdog_stop.clear()
    app._stall_watchdog_thread = threading.Thread(
        target=lambda: stall_watchdog_loop(app),
        name=_WATCHDOG_THREAD_NAME,
        daemon=True,
    )
    app._stall_watchdog_thread.start()


def stop_stall_watchdog(app) -> None:
    """Stop the stall watchdog thread."""
    app._stall_watchdog_stop.set()
    thread = app._stall_watchdog_thread
    if thread and thread.is_alive():
        try:
            thread.join(timeout=0.2)
        except Exception:
            pass
    app._stall_watchdog_thread = None


def stall_watchdog_loop(app) -> None:
    """Capture Python stack traces when the main loop appears blocked."""
    while not app._stall_watchdog_stop.wait(0.1):
        last = app._last_heartbeat_at
        if not app._timing_debug or last is None:
            continue
        now = time.monotonic()
        delta = now - last
        if delta < app._stall_watchdog_threshold_s:
            continue
        # Avoid spamming stack dumps while blocked.
        if now - app._last_stall_dump_at < 1.5:
            continue
        app._last_stall_dump_at = now

        thread_id = app._thread_id
        if thread_id is None:
            continue
        frame = sys._current_frames().get(thread_id)
        if frame is None:
            continue
        stack = "".join(traceback.format_stack(frame, limit=40))
        tui_log(
            "[TIMING] TextualApp.main_loop_stall_stack " f"{delta * 1000.0:.1f}ms thread_id={thread_id}\n{stack}",
        )


def heartbeat_tick(app) -> None:
    """Log event-loop stalls when timing debug is enabled."""
    now = time.monotonic()
    last = app._last_heartbeat_at
    app._last_heartbeat_at = now
    if not app._timing_debug or last is None:
        return

    delta = now - last
    # 250ms+ main-loop gaps are typically perceived as input lag.
    if delta >= 0.25:
        try:
            batch_len = len(app._event_batch)
        except Exception:
            batch_len = -1
        tui_log(
            "[TIMING] TextualApp.main_loop_stall " f"{delta * 1000.0:.1f}ms event_batch={batch_len} pending_flush={app._pending_flush}",
        )


def dump_widget_sizes(app) -> None:
    """Dump full widget tree with sizes for debugging layout issues."""

    def get_widget_info(widget, depth=0):
        """Recursively get widget info."""
        info = {
            "type": type(widget).__name__,
            "id": widget.id,
            "classes": list(widget.classes) if hasattr(widget, "classes") else [],
            "size": {"width": widget.size.width, "height": widget.size.height} if hasattr(widget, "size") else None,
            "region": {"x": widget.region.x, "y": widget.region.y, "width": widget.region.width, "height": widget.region.height} if hasattr(widget, "region") else None,
            "content_size": {"width": widget.content_size.width, "height": widget.content_size.height} if hasattr(widget, "content_size") else None,
            "styles": {
                "width": str(widget.styles.width) if hasattr(widget.styles, "width") else None,
                "height": str(widget.styles.height) if hasattr(widget.styles, "height") else None,
                "padding": str(widget.styles.padding) if hasattr(widget.styles, "padding") else None,
                "margin": str(widget.styles.margin) if hasattr(widget.styles, "margin") else None,
                "border": str(widget.styles.border) if hasattr(widget.styles, "border") else None,
            },
            "children": [],
        }
        if depth < 8:  # Limit depth to avoid huge dumps
            for child in widget.children:
                info["children"].append(get_widget_info(child, depth + 1))
        return info

    tree = get_widget_info(app)
    _widget_path = os.path.join(tempfile.gettempdir(), "widget_sizes.json")
    with open(_widget_path, "w") as f:
        json.dump(tree, f, indent=2, default=str)

    # Also dump specific timeline info to separate file for easier debugging
    timeline_debug = []
    try:
        from massgen.frontend.displays.textual_widgets.content_sections import (
            TimelineSection,
        )

        for ts in app.query(TimelineSection):
            ts_info = {
                "id": ts.id,
                "size": {"width": ts.size.width, "height": ts.size.height},
                "region": {"x": ts.region.x, "y": ts.region.y, "width": ts.region.width, "height": ts.region.height},
                "content_size": {"width": ts.content_size.width, "height": ts.content_size.height},
            }
            # Get the scroll container
            try:
                container = ts.query_one("#timeline_container")
                ts_info["container"] = {
                    "type": type(container).__name__,
                    "size": {"width": container.size.width, "height": container.size.height},
                    "region": {"x": container.region.x, "y": container.region.y, "width": container.region.width, "height": container.region.height},
                    "content_size": {"width": container.content_size.width, "height": container.content_size.height},
                    "virtual_size": {"width": container.virtual_size.width, "height": container.virtual_size.height},
                    "scroll_y": container.scroll_y,
                    "max_scroll_y": container.max_scroll_y,
                    "children_count": len(list(container.children)),
                    "children": [],
                }
                # Get first and last few children for debugging
                children = list(container.children)
                for i, child in enumerate(children[:5]):  # First 5
                    ts_info["container"]["children"].append(
                        {
                            "index": i,
                            "type": type(child).__name__,
                            "id": child.id,
                            "classes": list(child.classes),
                            "size": {"width": child.size.width, "height": child.size.height},
                            "region": {"y": child.region.y, "height": child.region.height},
                        },
                    )
                if len(children) > 10:
                    ts_info["container"]["children"].append({"...": f"{len(children) - 10} more items..."})
                for i, child in enumerate(children[-5:]):  # Last 5
                    if len(children) > 5:
                        ts_info["container"]["children"].append(
                            {
                                "index": len(children) - 5 + i,
                                "type": type(child).__name__,
                                "id": child.id,
                                "classes": list(child.classes),
                                "size": {"width": child.size.width, "height": child.size.height},
                                "region": {"y": child.region.y, "height": child.region.height},
                            },
                        )
            except Exception as e:
                ts_info["container_error"] = str(e)
            timeline_debug.append(ts_info)
    except Exception as e:
        timeline_debug.append({"error": str(e)})

    _timeline_path = os.path.join(tempfile.gettempdir(), "timeline_debug.json")
    with open(_timeline_path, "w") as f:
        json.dump(timeline_debug, f, indent=2, default=str)

    tui_log(f"Widget sizes dumped to {_widget_path} and {_timeline_path}")
