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

import sys
from pathlib import Path
from typing import Optional, Any
from loguru import logger

# Remove default logger to have full control
logger.remove()

# Global debug flag
_DEBUG_MODE = False


def setup_logging(debug: bool = False, log_file: Optional[str] = None):
    """
    Configure MassGen logging system using loguru.
    
    Args:
        debug: Enable debug mode with verbose logging
        log_file: Optional path to log file for persistent logging
    """
    global _DEBUG_MODE
    _DEBUG_MODE = debug
    
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
            
            return f"<green>{{time:HH:mm:ss.SSS}}</green> | <level>{{level: <8}}</level> | <{name_color}>{{name}}</{name_color}>:<{name_color}>{{function}}</{name_color}>:<{name_color}>{{line}}</{name_color}> - {{message}}\n{{exception}}"
        
        logger.add(
            sys.stderr,
            format=custom_format,
            level="DEBUG",
            colorize=True,
            backtrace=True,
            diagnose=True
        )
        
        # Also log to file in debug mode
        if not log_file:
            log_file = "massgen_debug.log"
        
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="100 MB",
            retention="1 week",
            compression="zip",
            backtrace=True,
            diagnose=True,
            enqueue=True  # Thread-safe logging
        )
        
        logger.info("Debug logging enabled - logging to console and file: {}", log_file)
    else:
        # Normal mode: only important messages
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO",
            colorize=True,
            filter=lambda record: record["level"].no >= logger.level("INFO").no
        )
        
        if log_file:
            logger.add(
                log_file,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
                level="INFO",
                rotation="10 MB",
                retention="3 days",
                compression="zip",
                enqueue=True
            )


def get_logger(name: str):
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically __name__ of the module)
    
    Returns:
        Configured logger instance
    """
    return logger.bind(name=name)


def log_orchestrator_activity(orchestrator_id: str, activity: str, details: dict = None):
    """
    Log orchestrator activities for debugging.
    
    Args:
        orchestrator_id: ID of the orchestrator
        activity: Description of the activity
        details: Additional details as dictionary
    """
    if _DEBUG_MODE:
        log = logger.bind(name=f"orchestrator.{orchestrator_id}")
        # Use magenta color for orchestrator activities
        log.opt(colors=True).debug("<magenta>🎯 {}: {}</magenta>", activity, details or {})


def log_agent_message(agent_id: str, direction: str, message: dict):
    """
    Log agent messages (sent/received) for debugging.
    
    Args:
        agent_id: ID of the agent
        direction: "SEND" or "RECV"
        message: Message content as dictionary
    """
    if _DEBUG_MODE:
        log = logger.bind(name=f"agent.{agent_id}")
        if direction == "SEND":
            # Use blue color for sent messages
            log.opt(colors=True).debug("<blue>📤 Sending message: {}</blue>", _format_message(message))
        elif direction == "RECV":
            # Use green color for received messages
            log.opt(colors=True).debug("<green>📥 Received message: {}</green>", _format_message(message))
        else:
            log.opt(colors=True).debug("<cyan>📨 {}: {}</cyan>", direction, _format_message(message))


def log_backend_activity(backend_name: str, activity: str, details: dict = None):
    """
    Log backend activities for debugging.
    
    Args:
        backend_name: Name of the backend (e.g., "openai", "claude")
        activity: Description of the activity
        details: Additional details as dictionary
    """
    if _DEBUG_MODE:
        log = logger.bind(name=f"backend.{backend_name}")
        # Use yellow color for backend activities
        log.opt(colors=True).debug("<yellow>⚙️ {}: {}</yellow>", activity, details or {})


def log_tool_call(agent_id: str, tool_name: str, arguments: dict, result: Any = None):
    """
    Log tool calls made by agents.
    
    Args:
        agent_id: ID of the agent making the tool call
        tool_name: Name of the tool being called
        arguments: Arguments passed to the tool
        result: Result returned by the tool (optional)
    """
    if _DEBUG_MODE:
        log = logger.bind(name=f"agent.{agent_id}.tools")
        if result is not None:
            # Use light gray color for tool calls
            log.opt(colors=True).debug("<light-black>🔧 Tool '{}' called with args: {} -> Result: {}</light-black>", 
                     tool_name, arguments, result)
        else:
            log.opt(colors=True).debug("<light-black>🔧 Calling tool '{}' with args: {}</light-black>", tool_name, arguments)


def log_coordination_step(step: str, details: dict = None):
    """
    Log coordination workflow steps.
    
    Args:
        step: Description of the coordination step
        details: Additional details as dictionary
    """
    if _DEBUG_MODE:
        log = logger.bind(name="coordination")
        # Use red color for coordination steps (distinctive from orchestrator)
        log.opt(colors=True).debug("<red>🔄 {}: {}</red>", step, details or {})


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
    "get_logger",
    "log_orchestrator_activity",
    "log_agent_message",
    "log_backend_activity",
    "log_tool_call",
    "log_coordination_step"
]