"""
Display implementations for MassGen v2 frontend.
"""

from typing import List, Optional
import time
from .base import StreamingDisplay


class SimpleStreamingDisplay(StreamingDisplay):
    """Simple terminal-based streaming display for MassGen v2 orchestrator output."""
    
    def __init__(self, 
                 show_agent_prefixes: bool = True,
                 show_events: bool = True,
                 show_timestamps: bool = False):
        """Initialize simple streaming display.
        
        Args:
            show_agent_prefixes: Whether to show [agent_id] prefixes
            show_events: Whether to show orchestrator events
            show_timestamps: Whether to show timestamps
        """
        super().__init__(
            show_agent_prefixes=show_agent_prefixes,
            show_events=show_events,
            show_timestamps=show_timestamps
        )
        self.show_agent_prefixes = show_agent_prefixes
        self.show_events = show_events
        self.show_timestamps = show_timestamps
    
    def initialize(self, question: str, agent_ids: List[str]) -> None:
        """Initialize the display with question and agent IDs."""
        self.agent_ids = agent_ids
        self.agent_outputs = {aid: [] for aid in agent_ids}
        
        print(f"🎯 MassGen v2 Coordination: {question}")
        print(f"👥 Agents: {', '.join(agent_ids)}")
        print("=" * 60)
    
    def display_content(self, source: Optional[str], content: str, chunk_type: str = "content") -> None:
        """Display content from a source (agent or orchestrator)."""
        if not content.strip():
            return
        
        clean_content = content.strip()
        
        # Add timestamp if requested
        timestamp = f"[{time.strftime('%H:%M:%S')}] " if self.show_timestamps else ""
        
        # Handle agent content
        if source and source in self.agent_ids:
            self._display_agent_content(source, clean_content, chunk_type, timestamp)
        
        # Handle orchestrator content
        elif source in ["coordination_hub", "orchestrator", None]:
            self._display_orchestrator_content(clean_content, timestamp)
        
        # Handle other sources
        else:
            print(f"{timestamp}[{source}] {clean_content}")
    
    def _display_agent_content(self, agent_id: str, content: str, chunk_type: str, timestamp: str) -> None:
        """Display content from a specific agent."""
        # Store content
        self._store_agent_output(agent_id, content)
        
        # Format prefix
        prefix = f"[{agent_id}] " if self.show_agent_prefixes else ""
        
        # Display based on type
        if "🔧" in content or chunk_type == "tool_calls":
            print(f"{timestamp}{prefix}🔧 {content}")
        elif any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]):
            print(f"{timestamp}{prefix}📊 {content}")
        else:
            print(f"{timestamp}{prefix}{content}", end="", flush=True)
    
    def _display_orchestrator_content(self, content: str, timestamp: str) -> None:
        """Display content from orchestrator."""
        # Handle coordination events
        if any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]) and self.show_events:
            clean_line = content.replace('**', '').replace('##', '').strip()
            if clean_line:
                event = f"🎭 {clean_line}"
                self._store_event(event)
                print(f"\n{timestamp}{event}")
        
        # Handle regular content
        elif not content.startswith('---') and not content.startswith('*Coordinated by'):
            print(f"{timestamp}{content}", end="", flush=True)
    
    def show_final_summary(self) -> None:
        """Show final coordination summary."""
        print(f"\n\n✅ Coordination completed with {len(self.agent_ids)} agents")
        print(f"📊 Total events: {len(self.orchestrator_events)}")
    
    def cleanup(self) -> None:
        """Clean up resources."""
        pass


class ColoredStreamingDisplay(SimpleStreamingDisplay):
    """Enhanced display with color coding and better formatting."""
    
    # ANSI color codes
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'dim': '\033[2m',
        'red': '\033[31m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'magenta': '\033[35m',
        'cyan': '\033[36m',
        'white': '\033[37m',
        'bright_red': '\033[91m',
        'bright_green': '\033[92m',
        'bright_yellow': '\033[93m',
        'bright_blue': '\033[94m',
        'bright_magenta': '\033[95m',
        'bright_cyan': '\033[96m'
    }
    
    def __init__(self, 
                 show_agent_prefixes: bool = True,
                 show_events: bool = True,
                 show_timestamps: bool = False,
                 use_colors: bool = True):
        """Initialize colored streaming display.
        
        Args:
            show_agent_prefixes: Whether to show [agent_id] prefixes
            show_events: Whether to show orchestrator events
            show_timestamps: Whether to show timestamps
            use_colors: Whether to use color output
        """
        super().__init__(show_agent_prefixes, show_events, show_timestamps)
        self.use_colors = use_colors
        self.agent_colors = {}
    
    def _colorize(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if not self.use_colors or color not in self.COLORS:
            return text
        return f"{self.COLORS[color]}{text}{self.COLORS['reset']}"
    
    def _get_agent_color(self, agent_id: str) -> str:
        """Get consistent color for an agent."""
        if agent_id not in self.agent_colors:
            # Assign colors in rotation
            color_options = ['blue', 'green', 'magenta', 'cyan', 'yellow']
            color_index = len(self.agent_colors) % len(color_options)
            self.agent_colors[agent_id] = color_options[color_index]
        return self.agent_colors[agent_id]
    
    def initialize(self, question: str, agent_ids: List[str]) -> None:
        """Initialize the display with question and agent IDs."""
        self.agent_ids = agent_ids
        self.agent_outputs = {aid: [] for aid in agent_ids}
        
        print(self._colorize("🎯 MassGen v2 Coordination:", 'bold') + f" {question}")
        
        # Color-code agent list
        colored_agents = []
        for agent_id in agent_ids:
            color = self._get_agent_color(agent_id)
            colored_agents.append(self._colorize(agent_id, color))
        
        print(f"👥 Agents: {', '.join(colored_agents)}")
        print(self._colorize("=" * 60, 'dim'))
    
    def _display_agent_content(self, agent_id: str, content: str, chunk_type: str, timestamp: str) -> None:
        """Display content from a specific agent with colors."""
        # Store content
        self._store_agent_output(agent_id, content)
        
        # Get agent color
        agent_color = self._get_agent_color(agent_id)
        
        # Format prefix with color
        if self.show_agent_prefixes:
            prefix = self._colorize(f"[{agent_id}]", agent_color) + " "
        else:
            prefix = ""
        
        # Display based on type with appropriate colors
        if "🔧" in content or chunk_type == "tool_calls":
            print(f"{timestamp}{prefix}{self._colorize('🔧', 'yellow')} {content}")
        elif any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]):
            status_color = 'green' if '✅' in content else 'bright_blue' if '🗳️' in content else 'yellow'
            print(f"{timestamp}{prefix}{self._colorize('📊', status_color)} {content}")
        else:
            print(f"{timestamp}{prefix}{content}", end="", flush=True)
    
    def _display_orchestrator_content(self, content: str, timestamp: str) -> None:
        """Display content from orchestrator with colors."""
        # Handle coordination events
        if any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]) and self.show_events:
            clean_line = content.replace('**', '').replace('##', '').strip()
            if clean_line:
                event = f"🎭 {clean_line}"
                self._store_event(event)
                colored_event = self._colorize(event, 'bright_magenta')
                print(f"\n{timestamp}{colored_event}")
        
        # Handle regular content
        elif not content.startswith('---') and not content.startswith('*Coordinated by'):
            print(f"{timestamp}{content}", end="", flush=True)
    
    def show_final_summary(self) -> None:
        """Show final coordination summary with colors."""
        summary = f"✅ Coordination completed with {len(self.agent_ids)} agents"
        events = f"📊 Total events: {len(self.orchestrator_events)}"
        
        print(f"\n\n{self._colorize(summary, 'bright_green')}")
        print(self._colorize(events, 'bright_blue'))