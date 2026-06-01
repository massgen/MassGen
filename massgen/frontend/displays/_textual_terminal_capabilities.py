"""Terminal capability detection for the Textual terminal display.

Extracted collaborator (step 1 of the textual_terminal_display refactor).

``TerminalCapabilityProbe`` is a pure value object: it inspects the process
environment (and the ``locale`` module) to decide whether the terminal supports
emoji, what kind of terminal it is, and what an adaptive refresh rate should be.
It has NO back-reference to the display/app and imports nothing from Textual, so
it is safe to import even when Textual is unavailable.

The ``EMOJI_FALLBACKS`` mapping lives here and is re-exported by
``textual_terminal_display`` for backward compatibility.
"""

from __future__ import annotations

import locale as _locale
import os
from collections.abc import Mapping
from dataclasses import dataclass

# Emoji fallback mapping for terminals without Unicode support
EMOJI_FALLBACKS = {
    "🚀": ">>",  # Launch
    "💡": "(!)",  # Question
    "🤖": "[A]",  # Agent
    "✅": "[✓]",  # Success
    "❌": "[X]",  # Error
    "🔄": "[↻]",  # Processing
    "📊": "[=]",  # Stats
    "🎯": "[>]",  # Target
    "⚡": "[!]",  # Fast
    "🎤": "[M]",  # Presentation
    "🔍": "[?]",  # Search/Evaluation
    "⚠️": "[!]",  # Warning
    "📋": "[□]",  # Summary
    "🧠": "[B]",  # Brain/Reasoning
}

# Adaptive refresh-rate table keyed by detected terminal type.
_ADAPTIVE_REFRESH_RATES = {
    "ssh": 4,
    "vscode": 4,
    "iterm": 10,
    "windows_terminal": 4,
    "unknown": 6,
}
_DEFAULT_REFRESH_RATE = 6


def detect_emoji_support(env: Mapping[str, str], *, on_error=None) -> bool:
    """Detect if the terminal supports emoji.

    Mirrors the legacy ``TextualTerminalDisplay._detect_emoji_support`` logic.
    ``on_error`` is an optional callback invoked with the exception if the
    locale lookup fails (used to preserve the existing tui_log side effect).
    """
    term_program = env.get("TERM_PROGRAM", "")
    if term_program in ["vscode", "iTerm.app", "Apple_Terminal"]:
        return True

    if env.get("WT_SESSION"):
        return True

    if env.get("WT_PROFILE_ID"):
        return True

    try:
        encoding = _locale.getpreferredencoding()
        if encoding.lower() in ["utf-8", "utf8"]:
            return True
    except Exception as e:  # pragma: no cover - exercised via display delegator
        if on_error is not None:
            on_error(e)

    lang = env.get("LANG", "")
    if "UTF-8" in lang or "utf8" in lang:
        return True

    return False


def detect_terminal_type(env: Mapping[str, str]) -> str:
    """Detect terminal type from environment signals."""
    if env.get("TERM_PROGRAM") == "vscode":
        return "vscode"

    if env.get("TERM_PROGRAM") == "iTerm.app":
        return "iterm"

    if env.get("SSH_CONNECTION") or env.get("SSH_CLIENT"):
        return "ssh"

    if env.get("WT_SESSION"):
        return "windows_terminal"

    return "unknown"


def get_adaptive_refresh_rate(terminal_type: str) -> int:
    """Get the optimal refresh rate for a detected terminal type."""
    return _ADAPTIVE_REFRESH_RATES.get(terminal_type, _DEFAULT_REFRESH_RATE)


def get_icon(emoji: str, *, emoji_support: bool) -> str:
    """Return the emoji or its ASCII fallback based on terminal support."""
    if emoji_support:
        return emoji
    return EMOJI_FALLBACKS.get(emoji, emoji)


@dataclass(frozen=True)
class TerminalCapabilityProbe:
    """Immutable snapshot of detected terminal capabilities."""

    emoji_support: bool
    terminal_type: str
    refresh_rate: int

    @classmethod
    def detect(cls, *, env: Mapping[str, str] | None = None, on_error=None) -> TerminalCapabilityProbe:
        """Probe the environment and produce a capability snapshot.

        ``refresh_rate`` is the adaptive rate for the detected terminal type;
        callers that received an explicit refresh rate should ignore it.
        """
        if env is None:
            env = os.environ
        terminal_type = detect_terminal_type(env)
        return cls(
            emoji_support=detect_emoji_support(env, on_error=on_error),
            terminal_type=terminal_type,
            refresh_rate=get_adaptive_refresh_rate(terminal_type),
        )
