"""
Base Display Interface for MassGen Coordination

Defines the interface that all display implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BaseDisplay(ABC):
    """Abstract base class for MassGen coordination displays."""

    def __init__(self, agent_ids: List[str], **kwargs):
        """Initialize display with agent IDs and configuration."""
        self.agent_ids = agent_ids
        self.agent_outputs = {agent_id: [] for agent_id in agent_ids}
        self.agent_status = {agent_id: "waiting" for agent_id in agent_ids}
        self.orchestrator_events = []
        self.config = kwargs

    @abstractmethod
    def initialize(self, question: str, log_filename: Optional[str] = None):
        """Initialize the display with question and optional log file."""
        pass

    @abstractmethod
    def update_agent_content(
        self, agent_id: str, content: str, content_type: str = "thinking"
    ):
        """Update content for a specific agent.

        Args:
            agent_id: The agent whose content to update
            content: The content to add/update
            content_type: Type of content ("thinking", "tool", "status")
        """
        pass

    @abstractmethod
    def update_agent_status(self, agent_id: str, status: str):
        """Update status for a specific agent.

        Args:
            agent_id: The agent whose status to update
            status: New status ("waiting", "working", "completed")
        """
        pass

    @abstractmethod
    def add_orchestrator_event(self, event: str):
        """Add an orchestrator coordination event.

        Args:
            event: The coordination event message
        """
        pass

    @abstractmethod
    def show_final_answer(self, answer: str, vote_results=None, selected_agent=None):
        """Display the final coordinated answer.

        Args:
            answer: The final coordinated answer
            vote_results: Dictionary of vote results (optional)
            selected_agent: The selected agent (optional)
        """
        pass

    @abstractmethod
    def cleanup(self):
        """Clean up display resources."""
        pass

    def get_agent_content(self, agent_id: str) -> List[str]:
        """Get all content for a specific agent."""
        return self.agent_outputs.get(agent_id, [])

    def get_agent_status(self, agent_id: str) -> str:
        """Get current status for a specific agent."""
        return self.agent_status.get(agent_id, "unknown")

    def get_orchestrator_events(self) -> List[str]:
        """Get all orchestrator events."""
        return self.orchestrator_events.copy()

    def process_reasoning_content(self, chunk_type: str, content: str, source: str) -> str:
        """Process reasoning content and add prefixes as needed.
        
        Args:
            chunk_type: Type of the chunk (e.g., "reasoning_summary")
            content: The content to process
            source: The source agent/component
            
        Returns:
            Processed content with prefix if needed
        """
        if chunk_type == "reasoning_summary":
            # Track if we're in an active summary for this source
            summary_active_key = f"_summary_active_{source}"
            
            if not hasattr(self, summary_active_key) or not getattr(self, summary_active_key, False):
                # Start of new summary - add prefix and mark as active
                setattr(self, summary_active_key, True)
                return f"📋 [Reasoning Summary] {content}"
            else:
                # Continuing existing summary - no prefix
                return content
                
        elif chunk_type == "reasoning_summary_done":
            # End of reasoning summary - reset flag
            summary_active_key = f"_summary_active_{source}"
            if hasattr(self, summary_active_key):
                setattr(self, summary_active_key, False)
                
        return content
