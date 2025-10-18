# -*- coding: utf-8 -*-
"""
Centralized logging configuration for MassGen using loguru.

This module provides a unified logging system for all MassGen components,
with special focus on debugging orchestrator and agent backend activities.

Color Scheme for Debug Logging:
- Magenta: Orchestrator activities (🎯)
- Blue: Messages sent from orchestrator to agents (📤)
- Green: Messages received from agents (📥)
- Yellow: Backend activities (⚙️)
- Cyan: General agent activities (📨)
- Light-black: Tool calls (🔧)
- Red: Coordination steps (🔄)
"""

import inspect
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# Remove default logger to have full control
logger.remove()

# Global debug flag
_DEBUG_MODE = False

# Global log session directory and turn tracking
_LOG_SESSION_DIR = None
_LOG_BASE_SESSION_DIR = None  # Base session dir (without turn subdirectory)
_CURRENT_TURN = None

# Console logging suppression (for Rich Live display compatibility)
_CONSOLE_HANDLER_ID = None
_CONSOLE_SUPPRESSED = False


def get_log_session_dir(turn: Optional[int] = None) -> Path:
    """Get the current log session directory.

    Args:
        turn: Optional turn number for multi-turn conversations

    Returns:
        Path to the log directory
    """
    global _LOG_SESSION_DIR, _LOG_BASE_SESSION_DIR, _CURRENT_TURN

    # Initialize base session dir once per session
    if _LOG_BASE_SESSION_DIR is None:
        # Check if we're running from within the MassGen development directory
        # by looking for pyproject.toml with massgen package
        cwd = Path.cwd()

        # Check if pyproject.toml exists and contains massgen package definition
        pyproject_file = cwd / "pyproject.toml"
        if pyproject_file.exists():
            try:
                content = pyproject_file.read_text()
                if 'name = "massgen"' in content:
                    pass
            except Exception:
                pass

        log_base_dir = Path(".massgen") / "massgen_logs"
        log_base_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped session directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _LOG_BASE_SESSION_DIR = log_base_dir / f"log_{timestamp}"
        _LOG_BASE_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    # If turn changed, update the directory
    if turn is not None and turn != _CURRENT_TURN:
        _CURRENT_TURN = turn
        _LOG_SESSION_DIR = None  # Force recreation

    if _LOG_SESSION_DIR is None:
        # Create directory structure based on turn
        if _CURRENT_TURN and _CURRENT_TURN > 0:
            # Multi-turn conversation: organize by turn within session
            _LOG_SESSION_DIR = _LOG_BASE_SESSION_DIR / f"turn_{_CURRENT_TURN}"
        else:
            # First execution or single execution: use base session dir
            _LOG_SESSION_DIR = _LOG_BASE_SESSION_DIR

        _LOG_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    return _LOG_SESSION_DIR


def save_execution_metadata(query: str, config_path: Optional[str] = None, config_content: Optional[dict] = None):
    """Save the query and config metadata to the log directory.

    This allows reconstructing what was executed in this session.

    Args:
        query: The user's query/prompt
        config_path: Path to the config file that was used (optional)
        config_content: The actual config dictionary (optional)
    """
    import yaml

    log_dir = get_log_session_dir()

    # Create a single metadata file with all execution info
    metadata = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
    }

    if config_path:
        metadata["config_path"] = str(config_path)

    if config_content:
        metadata["config"] = config_content

    metadata_file = log_dir / "execution_metadata.yaml"
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            yaml.dump(metadata, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        logger.info(f"Saved execution metadata to: {metadata_file}")
    except Exception as e:
        logger.warning(f"Failed to save execution metadata: {e}")


def setup_logging(debug: bool = False, log_file: Optional[str] = None, turn: Optional[int] = None):
    """
    Configure MassGen logging system using loguru.

    Args:
        debug: Enable debug mode with verbose logging
        log_file: Optional path to log file for persistent logging
        turn: Optional turn number for multi-turn conversations
    """
    global _DEBUG_MODE, _CONSOLE_HANDLER_ID, _CONSOLE_SUPPRESSED
    _DEBUG_MODE = debug
    _CONSOLE_SUPPRESSED = False

    # Remove all existing handlers
    logger.remove()

    if debug:
        # Debug mode: verbose console output with full details
        def custom_format(record):
            # Color code the module name based on category
            name = record["extra"].get("name", "")
            if "orchestrator" in name:
                name_color = "magenta"
            elif "backend" in name:
                name_color = "yellow"
            elif "agent" in name:
                name_color = "cyan"
            elif "coordination" in name:
                name_color = "red"
            else:
                name_color = "white"

            # Format the name to be more readable
            formatted_name = name if name else "{name}"

            return (
                f"<green>{{time:HH:mm:ss.SSS}}</green> | <level>{{level: <8}}</level> | "
                f"<{name_color}>{formatted_name}</{name_color}>:<{name_color}>{{function}}</{name_color}>:"
                f"<{name_color}>{{line}}</{name_color}> - {{message}}\n{{exception}}"
            )

        _CONSOLE_HANDLER_ID = logger.add(
            sys.stderr,
            format=custom_format,
            level="DEBUG",
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

        # Also log to file in debug mode
        if not log_file:
            log_session_dir = get_log_session_dir(turn=turn)
            log_file = log_session_dir / "massgen_debug.log"

        logger.add(
            str(log_file),
            format=custom_format,
            level="DEBUG",
            rotation="100 MB",
            retention="1 week",
            compression="zip",
            backtrace=True,
            diagnose=True,
            enqueue=True,  # Thread-safe logging
            colorize=False,  # Keep color codes in file
        )

        logger.info("Debug logging enabled - logging to console and file: {}", log_file)
    else:
        # Normal mode: only important messages to console, but all INFO+ to file
        console_format = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"

        _CONSOLE_HANDLER_ID = logger.add(
            sys.stderr,
            format=console_format,
            level="WARNING",  # Only show WARNING and above on console in non-debug mode
            colorize=True,
        )

        # Always create log file in non-debug mode to capture INFO messages
        if not log_file:
            log_session_dir = get_log_session_dir(turn=turn)
            log_file = log_session_dir / "massgen.log"

        # Use the same format as console with color codes
        logger.add(
            str(log_file),
            format=console_format,
            level="INFO",  # Capture INFO and above in file
            rotation="10 MB",
            retention="3 days",
            compression="zip",
            enqueue=True,
            colorize=False,  # Keep color codes in file
        )

        logger.info("Logging enabled - logging INFO+ to file: {}", log_file)


def suppress_console_logging():
    """
    Temporarily suppress console logging to prevent interference with Rich Live display.

    This removes the console handler while keeping file logging active.
    Call restore_console_logging() to re-enable console output.
    """
    global _CONSOLE_HANDLER_ID, _CONSOLE_SUPPRESSED

    if _CONSOLE_HANDLER_ID is not None and not _CONSOLE_SUPPRESSED:
        try:
            logger.remove(_CONSOLE_HANDLER_ID)
            _CONSOLE_SUPPRESSED = True
        except ValueError:
            # Handler already removed
            pass


def restore_console_logging():
    """
    Restore console logging after it was suppressed.

    Re-adds the console handler with the same settings that were used during setup.
    """
    global _CONSOLE_HANDLER_ID, _CONSOLE_SUPPRESSED, _DEBUG_MODE

    if not _CONSOLE_SUPPRESSED:
        return

    # Re-add console handler with same settings as setup_logging
    if _DEBUG_MODE:

        def custom_format(record):
            name = record["extra"].get("name", "")
            if "orchestrator" in name:
                name_color = "magenta"
            elif "backend" in name:
                name_color = "yellow"
            elif "agent" in name:
                name_color = "cyan"
            elif "coordination" in name:
                name_color = "red"
            else:
                name_color = "white"
            formatted_name = name if name else "{name}"
            return (
                f"<green>{{time:HH:mm:ss.SSS}}</green> | <level>{{level: <8}}</level> | "
                f"<{name_color}>{formatted_name}</{name_color}>:<{name_color}>{{function}}</{name_color}>:"
                f"<{name_color}>{{line}}</{name_color}> - {{message}}\n{{exception}}"
            )

        _CONSOLE_HANDLER_ID = logger.add(
            sys.stderr,
            format=custom_format,
            level="DEBUG",
            colorize=True,
            backtrace=True,
            diagnose=True,
        )
    else:
        console_format = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        _CONSOLE_HANDLER_ID = logger.add(
            sys.stderr,
            format=console_format,
            level="WARNING",
            colorize=True,
        )

    _CONSOLE_SUPPRESSED = False


def get_logger(name: str):
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Configured logger instance
    """
    return logger.bind(name=name)


def _get_caller_info():
    """
    Get the caller's line number and function name from the stack frame.

    Returns:
        Tuple of (function_name, line_number where the logging function was called)
    """
    frame = inspect.currentframe()
    # Stack frames:
    # - frame: _get_caller_info (this function)
    # - frame.f_back: log_orchestrator_agent_message or log_backend_agent_message
    # - frame.f_back.f_back: the actual caller (e.g., _stream_agent_execution)

    if frame and frame.f_back and frame.f_back.f_back:
        caller_frame = frame.f_back.f_back
        function_name = caller_frame.f_code.co_name
        # Get the line number where the logging function was called from within the caller
        line_number = caller_frame.f_lineno
        return function_name, line_number
    return "unknown", 0


def log_orchestrator_activity(orchestrator_id: str, activity: str, details: dict = None):
    """
    Log orchestrator activities for debugging.

    Args:
        orchestrator_id: ID of the orchestrator
        activity: Description of the activity
        details: Additional details as dictionary
    """
    # Get caller information
    func_name, line_num = _get_caller_info()
    log = logger.bind(name=f"orchestrator.{orchestrator_id}:{func_name}:{line_num}")
    if _DEBUG_MODE:
        # Use magenta color for orchestrator activities
        log.opt(colors=True).debug("<magenta>🎯 {}: {}</magenta>", activity, details or {})


def log_agent_message(agent_id: str, direction: str, message: dict, backend_name: str = None):
    """
    Log agent messages (sent/received) for debugging.

    Args:
        agent_id: ID of the agent
        direction: "SEND" or "RECV"
        message: Message content as dictionary
        backend_name: Optional name of the backend provider
    """
    # Build a descriptive name with both agent ID and backend
    if backend_name:
        log_name = f"{agent_id}.{backend_name}"
        log = logger.bind(name=log_name)
    else:
        log_name = agent_id
        log = logger.bind(name=log_name)

    if _DEBUG_MODE:
        if direction == "SEND":
            # Use blue color for sent messages
            log.opt(colors=True).debug(
                "<blue>📤 [{}] Sending message: {}</blue>",
                log_name,
                _format_message(message),
            )
        elif direction == "RECV":
            # Use green color for received messages
            log.opt(colors=True).debug(
                "<green>📥 [{}] Received message: {}</green>",
                log_name,
                _format_message(message),
            )
        else:
            log.opt(colors=True).debug(
                "<cyan>📨 [{}] {}: {}</cyan>",
                log_name,
                direction,
                _format_message(message),
            )


def log_orchestrator_agent_message(agent_id: str, direction: str, message: dict, backend_name: str = None):
    """
    Log orchestrator-to-agent messages for debugging.

    Args:
        agent_id: ID of the agent
        direction: "SEND" or "RECV"
        message: Message content as dictionary
        backend_name: Optional name of the backend provider
    """
    # Get caller information
    func_name, line_num = _get_caller_info()

    # Build a descriptive name with orchestrator prefix
    if backend_name:
        log_name = f"orchestrator→{agent_id}.{backend_name}:{func_name}:{line_num}"
        log = logger.bind(name=log_name)
    else:
        log_name = f"orchestrator→{agent_id}:{func_name}:{line_num}"
        log = logger.bind(name=log_name)

    if _DEBUG_MODE:
        if direction == "SEND":
            # Use magenta color for orchestrator sent messages
            log.opt(colors=True).debug(
                "<magenta>🎯📤 [{}] Orchestrator sending to agent: {}</magenta>",
                log_name,
                _format_message(message),
            )
        elif direction == "RECV":
            # Use magenta color for orchestrator received messages
            log.opt(colors=True).debug(
                "<magenta>🎯📥 [{}] Orchestrator received from agent: {}</magenta>",
                log_name,
                _format_message(message),
            )
        else:
            log.opt(colors=True).debug(
                "<magenta>🎯📨 [{}] {}: {}</magenta>",
                log_name,
                direction,
                _format_message(message),
            )


def log_backend_agent_message(agent_id: str, direction: str, message: dict, backend_name: str = None):
    """
    Log backend-to-LLM messages for debugging.

    Args:
        agent_id: ID of the agent
        direction: "SEND" or "RECV"
        message: Message content as dictionary
        backend_name: Optional name of the backend provider
    """
    # Get caller information
    func_name, line_num = _get_caller_info()

    # Build a descriptive name with backend prefix
    if backend_name:
        log_name = f"backend.{backend_name}→{agent_id}:{func_name}:{line_num}"
        log = logger.bind(name=log_name)
    else:
        log_name = f"backend→{agent_id}:{func_name}:{line_num}"
        log = logger.bind(name=log_name)

    if _DEBUG_MODE:
        if direction == "SEND":
            # Use yellow color for backend sent messages
            log.opt(colors=True).debug(
                "<yellow>⚙️📤 [{}] Backend sending to LLM: {}</yellow>",
                log_name,
                _format_message(message),
            )
        elif direction == "RECV":
            # Use yellow color for backend received messages
            log.opt(colors=True).debug(
                "<yellow>⚙️📥 [{}] Backend received from LLM: {}</yellow>",
                log_name,
                _format_message(message),
            )
        else:
            log.opt(colors=True).debug(
                "<yellow>⚙️📨 [{}] {}: {}</yellow>",
                log_name,
                direction,
                _format_message(message),
            )


def log_backend_activity(backend_name: str, activity: str, details: dict = None, agent_id: str = None):
    """
    Log backend activities for debugging.

    Args:
        backend_name: Name of the backend (e.g., "openai", "claude")
        activity: Description of the activity
        details: Additional details as dictionary
        agent_id: Optional ID of the agent using this backend
    """
    # Get caller information
    func_name, line_num = _get_caller_info()

    # Build a descriptive name with both agent ID and backend
    if agent_id:
        log_name = f"{agent_id}.{backend_name}"
        log = logger.bind(name=f"{log_name}:{func_name}:{line_num}")
    else:
        log_name = backend_name
        log = logger.bind(name=f"backend.{backend_name}:{func_name}:{line_num}")

    if _DEBUG_MODE:
        # Use yellow color for backend activities
        log.opt(colors=True).debug("<yellow>⚙️ [{}] {}: {}</yellow>", log_name, activity, details or {})


def log_mcp_activity(backend_name: str, message: str, details: dict = None, agent_id: str = None):
    """
    Log MCP (Model Context Protocol) activities at INFO level.

    Args:
        backend_name: Name of the backend (e.g., "claude", "openai")
        message: Description of the MCP activity
        details: Additional details as dictionary
        agent_id: Optional ID of the agent using this backend
    """
    func_name, line_num = _get_caller_info()

    if agent_id:
        log_name = f"{agent_id}.{backend_name}"
        log = logger.bind(name=f"{log_name}:{func_name}:{line_num}")
    else:
        log_name = backend_name
        log = logger.bind(name=f"backend.{backend_name}:{func_name}:{line_num}")

    log.info("MCP: {} - {}", message, details or {})


def log_tool_call(
    agent_id: str,
    tool_name: str,
    arguments: dict,
    result: Any = None,
    backend_name: str = None,
):
    """
    Log tool calls made by agents.

    Args:
        agent_id: ID of the agent making the tool call
        tool_name: Name of the tool being called
        arguments: Arguments passed to the tool
        result: Result returned by the tool (optional)
        backend_name: Optional name of the backend provider
    """
    # Build a descriptive name with both agent ID and backend
    if backend_name:
        log_name = f"{agent_id}.{backend_name}"
        log = logger.bind(name=f"{log_name}.tools")
    else:
        log_name = agent_id
        log = logger.bind(name=f"{agent_id}.tools")

    if _DEBUG_MODE:
        if result is not None:
            # Use light gray color for tool calls
            log.opt(colors=True).debug(
                "<light-black>🔧 [{}] Tool '{}' called with args: {} -> Result: {}</light-black>",
                log_name,
                tool_name,
                arguments,
                result,
            )
        else:
            log.opt(colors=True).debug(
                "<light-black>🔧 [{}] Calling tool '{}' with args: {}</light-black>",
                log_name,
                tool_name,
                arguments,
            )


def log_coordination_step(step: str, details: dict = None):
    """
    Log coordination workflow steps.

    Args:
        step: Description of the coordination step
        details: Additional details as dictionary
    """
    log = logger.bind(name="coordination")
    if _DEBUG_MODE:
        # Use red color for coordination steps (distinctive from orchestrator)
        log.opt(colors=True).debug("<red>🔄 {}: {}</red>", step, details or {})


def log_stream_chunk(source: str, chunk_type: str, content: Any = None, agent_id: str = None):
    """
    Log stream chunks at INFO level (always logged to file).

    Args:
        source: Source of the stream chunk (e.g., "orchestrator", "backend.claude_code")
        chunk_type: Type of the chunk (e.g., "content", "tool_call", "error")
        content: Content of the chunk
        agent_id: Optional agent ID for context
    """
    # Get caller information from the actual caller (not this function)
    frame = inspect.currentframe()
    # Stack frames:
    # - frame: log_stream_chunk (this function)
    # - frame.f_back: the actual caller (e.g., _present_final_answer)

    if frame and frame.f_back:
        caller_frame = frame.f_back
        function_name = caller_frame.f_code.co_name
        line_number = caller_frame.f_lineno
    else:
        function_name = "unknown"
        line_number = 0

    if agent_id:
        log_name = f"{source}.{agent_id}"
    else:
        log_name = source

    # Create a custom logger that will show the source name instead of module path
    log = logger.bind(name=f"{log_name}:{function_name}:{line_number}")

    # Always log stream chunks at INFO level (will go to file)
    # Format content based on type
    if content:
        if isinstance(content, dict):
            log.info("Stream chunk [{}]: {}", chunk_type, content)
        else:
            # No truncation - show full content
            log.info("Stream chunk [{}]: {}", chunk_type, content)
    else:
        log.info("Stream chunk [{}]", chunk_type)


def _format_message(message: dict) -> str:
    """
    Format message for logging without truncation.

    Args:
        message: Message dictionary

    Returns:
        Formatted message string
    """
    if not message:
        return "<empty>"

    # Format based on message type
    if "role" in message and "content" in message:
        content = message.get("content", "")
        if isinstance(content, str):
            # No truncation - show full content
            return f"[{message['role']}] {content}"
        else:
            return f"[{message['role']}] {str(content)}"

    # For other message types, just stringify without truncation
    msg_str = str(message)
    return msg_str


# Export main components
__all__ = [
    "logger",
    "setup_logging",
    "suppress_console_logging",
    "restore_console_logging",
    "get_logger",
    "get_log_session_dir",
    "save_execution_metadata",
    "log_orchestrator_activity",
    "log_agent_message",
    "log_orchestrator_agent_message",
    "log_backend_agent_message",
    "log_backend_activity",
    "log_mcp_activity",
    "log_tool_call",
    "log_coordination_step",
    "log_stream_chunk",
]
