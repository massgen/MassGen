"""
Base classes for frontend display components.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class StreamingDisplay(ABC):
    """Abstract base class for streaming display implementations."""
    
    def __init__(self, **kwargs):
        """Initialize display with configuration options."""
        self.config = kwargs
        self.agent_ids: List[str] = []
        self.agent_outputs: Dict[str, List[str]] = {}
        self.orchestrator_events: List[str] = []
    
    @abstractmethod
    def initialize(self, question: str, agent_ids: List[str]) -> None:
        """
        Initialize the display for a new coordination session.
        
        Args:
            question: The question being coordinated on
            agent_ids: List of agent identifiers participating
        """
        pass
    
    @abstractmethod
    def display_content(self, source: Optional[str], content: str, chunk_type: str = "content") -> None:
        """
        Display content from a source (agent or orchestrator).
        
        Args:
            source: Source identifier (agent_id, "orchestrator", etc.)
            content: Content to display
            chunk_type: Type of content ("content", "tool_calls", "done", etc.)
        """
        pass
    
    @abstractmethod
    def show_final_summary(self) -> None:
        """Show final coordination summary."""
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources and finalize display."""
        pass
    
    # Common utility methods
    def _store_agent_output(self, agent_id: str, content: str) -> None:
        """Store agent output for later reference."""
        if agent_id not in self.agent_outputs:
            self.agent_outputs[agent_id] = []
        self.agent_outputs[agent_id].append(content)
    
    def _store_event(self, event: str) -> None:
        """Store orchestrator event for later reference."""
        self.orchestrator_events.append(event)
    
    def get_agent_output(self, agent_id: str) -> List[str]:
        """Get all output from a specific agent."""
        return self.agent_outputs.get(agent_id, [])
    
    def get_all_events(self) -> List[str]:
        """Get all orchestrator events."""
        return self.orchestrator_events.copy()