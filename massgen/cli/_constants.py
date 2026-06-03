#!/usr/bin/env python3
"""Shared constants for the massgen.cli package: ANSI colors, exit codes, and styles.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    pass

from prompt_toolkit.styles import Style

# Session storage is internal state management - HARDCODED, NOT CONFIGURABLE
# Old configs with orchestrator.session_storage are backwards compatible (value ignored)
SESSION_STORAGE = ".massgen/sessions"


# Color constants for terminal output
BRIGHT_CYAN = "\033[96m"


BRIGHT_BLUE = "\033[94m"


BRIGHT_GREEN = "\033[92m"


BRIGHT_YELLOW = "\033[93m"


BRIGHT_MAGENTA = "\033[95m"


BRIGHT_RED = "\033[91m"


BRIGHT_WHITE = "\033[97m"


RESET = "\033[0m"


BOLD = "\033[1m"


# Exit code constants for automation mode
EXIT_SUCCESS = 0  # Coordination completed successfully


EXIT_CONFIG_ERROR = 1  # Configuration or validation error


EXIT_EXECUTION_ERROR = 2  # Agent failure, API error, or execution error


EXIT_TIMEOUT = 3  # Orchestrator or agent timeout


EXIT_INTERRUPTED = 4  # KeyboardInterrupt (Ctrl+C)


# Custom questionary style for polished selection interface
MASSGEN_QUESTIONARY_STYLE = Style(
    [
        ("qmark", "fg:#00d7ff bold"),  # Bright cyan question mark
        ("question", "fg:#ffffff bold"),  # White question text
        ("answer", "fg:#00d7ff bold"),  # Bright cyan answer
        ("pointer", "fg:#00d7ff bold"),  # Bright cyan pointer (▸)
        ("highlighted", "fg:#00d7ff bold"),  # Bright cyan highlighted option
        ("selected", "fg:#00ff87"),  # Bright green selected
        ("separator", "fg:#6c6c6c"),  # Gray separators
        ("instruction", "fg:#808080"),  # Gray instructions
        ("text", "fg:#ffffff"),  # White text
        ("disabled", "fg:#6c6c6c italic"),  # Gray disabled
    ],
)


_MASSGEN_WORKSPACES_PREFIX = ".massgen/workspaces/"
