"""
MassGen v2 Simple Frontend

A minimal streaming frontend for displaying MassGen orchestrator output.
Based on the reference implementation in ../mass/mass/frontend.
"""

from typing import Optional, List, Dict, Any, AsyncGenerator
import asyncio


class SimpleStreamingDisplay:
    """Simple streaming display for MassGen v2 orchestrator output."""
    
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
        self.show_agent_prefixes = show_agent_prefixes
        self.show_events = show_events
        self.show_timestamps = show_timestamps
        self.agent_ids = []
        self.agent_outputs = {}
        self.orchestrator_events = []
    
    def initialize(self, question: str, agent_ids: List[str]):
        """Initialize the display with question and agent IDs."""
        self.agent_ids = agent_ids
        self.agent_outputs = {aid: [] for aid in agent_ids}
        
        print(f"🎯 MassGen v2 Coordination: {question}")
        print(f"👥 Agents: {', '.join(agent_ids)}")
        print("=" * 60)
    
    def display_content(self, source: Optional[str], content: str, chunk_type: str = "content"):
        """Display content from a source (agent or orchestrator)."""
        if not content.strip():
            return
        
        clean_content = content.strip()
        
        # Handle agent content
        if source and source in self.agent_ids:
            self._display_agent_content(source, clean_content, chunk_type)
        
        # Handle orchestrator content
        elif source in ["coordination_hub", "orchestrator", None]:
            self._display_orchestrator_content(clean_content)
        
        # Handle other sources
        else:
            print(f"[{source}] {clean_content}")
    
    def _display_agent_content(self, agent_id: str, content: str, chunk_type: str):
        """Display content from a specific agent."""
        # Store content
        self.agent_outputs[agent_id].append(content)
        
        # Format prefix
        prefix = f"[{agent_id}] " if self.show_agent_prefixes else ""
        
        # Display based on type
        if "🔧" in content or chunk_type == "tool_calls":
            print(f"{prefix}🔧 {content}")
        elif any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]):
            print(f"{prefix}📊 {content}")
        else:
            print(f"{prefix}{content}", end="", flush=True)
    
    def _display_orchestrator_content(self, content: str):
        """Display content from orchestrator."""
        # Handle coordination events
        if any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]) and self.show_events:
            clean_line = content.replace('**', '').replace('##', '').strip()
            if clean_line:
                event = f"🎭 {clean_line}"
                self.orchestrator_events.append(event)
                print(f"\n{event}")
        
        # Handle regular content
        elif not content.startswith('---') and not content.startswith('*Coordinated by'):
            print(content, end="", flush=True)
    
    def show_final_summary(self):
        """Show final coordination summary."""
        print(f"\n\n✅ Coordination completed with {len(self.agent_ids)} agents")
        print(f"📊 Total events: {len(self.orchestrator_events)}")
    
    def cleanup(self):
        """Clean up resources."""
        pass


class StreamingFrontend:
    """Main streaming frontend for MassGen v2."""
    
    def __init__(self, 
                 display: Optional[SimpleStreamingDisplay] = None,
                 **display_kwargs):
        """Initialize streaming frontend.
        
        Args:
            display: Custom display instance
            **display_kwargs: Arguments passed to default display
        """
        self.display = display or SimpleStreamingDisplay(**display_kwargs)
    
    async def coordinate(self, orchestrator, question: str) -> str:
        """Coordinate agents with streaming display.
        
        Args:
            orchestrator: MassGen v2 orchestrator instance
            question: Question for coordination
            
        Returns:
            Final coordinated response
        """
        # Get agent IDs from orchestrator
        agent_ids = list(orchestrator.agents.keys())
        
        # Initialize display
        self.display.initialize(question, agent_ids)
        
        try:
            # Process coordination stream
            full_response = ""
            messages = [{"role": "user", "content": question}]
            
            async for chunk in orchestrator.chat(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    content = chunk.content
                    source = getattr(chunk, 'source', None)
                    chunk_type = getattr(chunk, 'type', 'content')
                    
                    # Accumulate full response
                    if chunk_type == "content":
                        full_response += content
                    
                    # Display content
                    self.display.display_content(source, content, chunk_type)
                
                elif chunk.type == "done":
                    break
                elif chunk.type == "error":
                    print(f"\n❌ Error: {chunk.error}")
                    break
            
            # Show final summary
            self.display.show_final_summary()
            
            return full_response
            
        except Exception as e:
            print(f"\n❌ Coordination error: {e}")
            raise
        finally:
            self.display.cleanup()


# Convenience function
async def stream_coordination(orchestrator, question: str, **display_kwargs) -> str:
    """Quick coordination with streaming display.
    
    Args:
        orchestrator: MassGen v2 orchestrator instance
        question: Question for coordination
        **display_kwargs: Arguments passed to display
        
    Returns:
        Final coordinated response
    """
    frontend = StreamingFrontend(**display_kwargs)
    return await frontend.coordinate(orchestrator, question)