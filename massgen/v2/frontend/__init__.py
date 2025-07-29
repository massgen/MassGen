"""
MassGen v2 Frontend Package

Streaming frontend components for displaying MassGen orchestrator output
with various display options and customization capabilities.

Components:
- StreamingDisplay: Base class for display implementations
- SimpleStreamingDisplay: Basic terminal-based streaming display
- StreamingFrontend: Main frontend coordinator
- stream_coordination: Convenience function for quick coordination

Usage:
    from massgen.v2.frontend import StreamingFrontend, SimpleStreamingDisplay
    
    # Basic usage
    from massgen.v2.frontend import stream_coordination
    result = await stream_coordination(orchestrator, "Your question?")
    
    # Custom display
    display = SimpleStreamingDisplay(show_agent_prefixes=True, show_events=True)
    frontend = StreamingFrontend(display=display)
    result = await frontend.coordinate(orchestrator, "Your question?")
"""

from .base import StreamingDisplay
from .displays import SimpleStreamingDisplay, ColoredStreamingDisplay
from .frontend import StreamingFrontend, stream_coordination

__all__ = [
    # Base classes
    "StreamingDisplay",
    
    # Display implementations
    "SimpleStreamingDisplay", 
    "ColoredStreamingDisplay",
    
    # Frontend coordinator
    "StreamingFrontend",
    "stream_coordination"
]