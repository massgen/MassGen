"""
MassGen v2 Frontend Coordinator

Main streaming frontend for coordinating display of MassGen orchestrator output.
"""

from typing import Optional, AsyncGenerator
from .base import StreamingDisplay
from .displays import SimpleStreamingDisplay


class StreamingFrontend:
    """Main streaming frontend for MassGen v2."""
    
    def __init__(self, 
                 display: Optional[StreamingDisplay] = None,
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