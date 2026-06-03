#!/usr/bin/env python3
"""Environment loading, logfire observability setup, and automation-mode printing.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import sys
from pathlib import Path
from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    pass

from dotenv import load_dotenv

# --- cross-module references within the cli package ---
from ._constants import BRIGHT_YELLOW, RESET

# When --stream-events is active, stdout is reserved for JSONL output, so
# _automation_print routes to stderr. Set by streaming._setup_event_streaming
# (which writes ``env._stream_events_active = True``).
_stream_events_active = False


# Load environment variables from .env files
def load_env_file():
    """Load environment variables from .env files.

    Search order (later files override earlier ones):
    1. MassGen package .env (development fallback)
    2. User home ~/.massgen/.env (global user config)
    3. User config ~/.config/massgen/.env
    4. Project configs/.env (project-specific, optional)
    5. Current directory .env (project-specific, highest priority)
    """
    # Load in priority order (later overrides earlier)
    load_dotenv(Path(__file__).parent / ".env")  # Package fallback
    load_dotenv(Path.home() / ".massgen" / ".env")  # User global
    load_dotenv(Path.home() / ".config" / "massgen" / ".env")  # User config
    load_dotenv(Path.cwd() / "configs" / ".env")  # Project configs
    load_dotenv()  # Current directory (highest priority)


def _setup_logfire_observability() -> bool:
    """Configure Logfire observability and instrument all LLM providers.

    This sets up structured logging/tracing via Logfire and instruments
    all supported LLM provider clients (OpenAI, Anthropic, Google GenAI).

    Returns:
        True if Logfire was successfully configured, False otherwise.
    """
    try:
        import logfire  # noqa: F401 - Check if logfire is installed
    except ImportError:
        print(
            f"{BRIGHT_YELLOW}⚠️  Logfire not installed. " f"Install with: pip install massgen[observability]{RESET}",
        )
        return False

    from ..logger_config import integrate_logfire_with_loguru
    from ..structured_logging import configure_observability, get_tracer

    success = configure_observability(enabled=True)
    if not success:
        return False

    integrate_logfire_with_loguru()
    # Instrument all LLM providers globally
    tracer = get_tracer()
    tracer.instrument_google_genai()  # Gemini
    tracer.instrument_openai()  # OpenAI-compatible APIs
    tracer.instrument_anthropic()  # Claude
    return True


def _automation_print(msg: str) -> None:
    """Print automation-mode status lines (LOG_DIR, STATUS, OUTPUT_FILE, etc.).

    When event streaming is active, stdout is reserved for JSONL, so these
    lines are routed to stderr instead. Always flush so background processes
    with piped stdout (block-buffered) emit lines immediately.
    """
    print(msg, file=sys.stderr if _stream_events_active else sys.stdout, flush=True)
