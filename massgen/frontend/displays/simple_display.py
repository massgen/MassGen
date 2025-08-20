"""
Simple Display for MassGen Coordination

Basic text output display for minimal use cases and debugging.
"""

from typing import Optional
from .base_display import BaseDisplay


class SimpleDisplay(BaseDisplay):
    """Simple text-based display with minimal formatting."""

    def __init__(self, agent_ids, **kwargs):
        """Initialize simple display."""
        super().__init__(agent_ids, **kwargs)
        self.show_agent_prefixes = kwargs.get("show_agent_prefixes", True)
        self.show_events = kwargs.get("show_events", True)

    def initialize(self, question: str, log_filename: Optional[str] = None):
        """Initialize the display."""
        print(f"🎯 MassGen Coordination: {question}")
        if log_filename:
            print(f"📁 Log file: {log_filename}")
        print(f"👥 Agents: {', '.join(self.agent_ids)}")
        print("=" * 50)

    def update_agent_content(
        self, agent_id: str, content: str, content_type: str = "thinking"
    ):
        """Update content for a specific agent."""
        if agent_id not in self.agent_ids:
            return

        # Clean content - remove any legacy agent prefixes to avoid duplication
        clean_content = content.strip()
        if clean_content.startswith(f"[{agent_id}]"):
            clean_content = clean_content[len(f"[{agent_id}]") :].strip()

        # Remove any legacy ** prefixes from orchestrator messages (kept for compatibility)
        if clean_content.startswith(f"🤖 **{agent_id}**"):
            clean_content = clean_content.replace(f"🤖 **{agent_id}**", "🤖").strip()

        # Store cleaned content
        self.agent_outputs[agent_id].append(clean_content)

        # Display immediately
        if self.show_agent_prefixes:
            prefix = f"[{agent_id}] "
        else:
            prefix = ""

        if content_type == "tool":
            # Filter out noise "Tool result" messages
            if "Tool result:" in clean_content:
                return  # Skip tool result messages as they're just noise
            print(f"{prefix}🔧 {clean_content}")
        elif content_type == "status":
            print(f"{prefix}📊 {clean_content}")
        elif content_type == "presentation":
            print(f"{prefix}🎤 {clean_content}")
        else:
            print(f"{prefix}{clean_content}")

    def update_agent_status(self, agent_id: str, status: str):
        """Update status for a specific agent."""
        if agent_id not in self.agent_ids:
            return

        self.agent_status[agent_id] = status
        if self.show_agent_prefixes:
            print(f"[{agent_id}] Status: {status}")
        else:
            print(f"Status: {status}")

    def add_orchestrator_event(self, event: str):
        """Add an orchestrator coordination event."""
        self.orchestrator_events.append(event)
        if self.show_events:
            print(f"🎭 {event}")

    def show_final_answer(self, answer: str, vote_results=None, selected_agent=None):
        """Display the final coordinated answer."""
        print("\n" + "=" * 50)
        print(f"🎯 FINAL ANSWER: {answer}")
        if selected_agent:
            print(f"✅ Selected by: {selected_agent}")
        if vote_results:
            vote_summary = ", ".join(
                [f"{agent}: {votes}" for agent, votes in vote_results.items()]
            )
            print(f"🗳️ Vote results: {vote_summary}")
        print("=" * 50)

    def cleanup(self):
        """Clean up resources."""
        print(f"\n✅ Coordination completed with {len(self.agent_ids)} agents")
        print(f"📊 Total orchestrator events: {len(self.orchestrator_events)}")
        for agent_id in self.agent_ids:
            print(f"📝 {agent_id}: {len(self.agent_outputs[agent_id])} content items")
