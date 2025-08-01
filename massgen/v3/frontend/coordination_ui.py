"""
MassGen Coordination UI

Main interface for coordinating agents with visual display and logging.
"""

from typing import Optional, List, Dict, Any, AsyncGenerator
from .displays.base_display import BaseDisplay
from .displays.terminal_display import TerminalDisplay
from .displays.simple_display import SimpleDisplay
from .displays.rich_terminal_display import RichTerminalDisplay, is_rich_available
from .logging.realtime_logger import RealtimeLogger


class CoordinationUI:
    """Main coordination interface with display and logging capabilities."""
    
    def __init__(self, 
                 display: Optional[BaseDisplay] = None,
                 logger: Optional[RealtimeLogger] = None,
                 display_type: str = "terminal",
                 logging_enabled: bool = True,
                 enable_final_presentation: bool = True,
                 **kwargs):
        """Initialize coordination UI.
        
        Args:
            display: Custom display instance (overrides display_type)
            logger: Custom logger instance  
            display_type: Type of display ("terminal", "simple", "rich_terminal", "textual_terminal")
            logging_enabled: Whether to enable real-time logging
            enable_final_presentation: Whether to ask winning agent to present final answer
            **kwargs: Additional configuration passed to display/logger
        """
        self.enable_final_presentation = enable_final_presentation
        self.display = display
        # Filter kwargs for logger (only pass logger-specific params)
        logger_kwargs = {k: v for k, v in kwargs.items() if k in ['filename', 'update_frequency']}
        self.logger = logger if logger is not None else (RealtimeLogger(**logger_kwargs) if logging_enabled else None)
        self.display_type = display_type
        self.config = kwargs
        
        # Will be set during coordination
        self.agent_ids = []
        self.orchestrator = None
    
    async def coordinate(self, orchestrator, question: str, agent_ids: Optional[List[str]] = None) -> str:
        """Coordinate agents with visual display and logging.
        
        Args:
            orchestrator: MassGen orchestrator instance
            question: Question for coordination
            agent_ids: Optional list of agent IDs (auto-detected if not provided)
            
        Returns:
            Final coordinated response
        """
        self.orchestrator = orchestrator
        
        # Auto-detect agent IDs if not provided
        if agent_ids is None:
            self.agent_ids = list(orchestrator.agents.keys())
        else:
            self.agent_ids = agent_ids
        
        # Initialize display if not provided
        if self.display is None:
            if self.display_type == "terminal":
                self.display = TerminalDisplay(self.agent_ids, **self.config)
            elif self.display_type == "simple":
                self.display = SimpleDisplay(self.agent_ids, **self.config)
            elif self.display_type == "rich_terminal":
                if not is_rich_available():
                    print("⚠️  Rich library not available. Falling back to terminal display.")
                    print("   Install with: pip install rich")
                    self.display = TerminalDisplay(self.agent_ids, **self.config)
                else:
                    self.display = RichTerminalDisplay(self.agent_ids, **self.config)
            else:
                raise ValueError(f"Unknown display type: {self.display_type}")
        
        # Pass orchestrator reference to display for backend info
        self.display.orchestrator = orchestrator
        
        # Initialize logger and display
        log_filename = None
        if self.logger:
            log_filename = self.logger.initialize_session(question, self.agent_ids)
            monitoring = self.logger.get_monitoring_commands()
            print(f"📁 Real-time log: {log_filename}")
            print(f"💡 Monitor with: {monitoring['tail']}")
            print()
        
        self.display.initialize(question, log_filename)
        
        try:
            # Process coordination stream
            full_response = ""
            final_answer = ""
            
            async for chunk in orchestrator.chat_simple(question):
                content = getattr(chunk, 'content', '') or ''
                source = getattr(chunk, 'source', None)
                chunk_type = getattr(chunk, 'type', '')
                
                # Handle agent status updates
                if chunk_type == "agent_status":
                    status = getattr(chunk, 'status', None)
                    if source and status:
                        self.display.update_agent_status(source, status)
                    continue

                # Handle builtin tool results
                elif chunk_type == "builtin_tool_results":
                    builtin_results = getattr(chunk, 'builtin_tool_results', [])
                    if builtin_results and source:
                        for result in builtin_results:
                            tool_type = result.get('tool_type', 'unknown')
                            status_result = result.get('status', 'unknown')
                            tool_msg = f"🔧 [{tool_type.title()}] {status_result.title()}"
                            
                            if tool_type in ['code_interpreter', 'code_execution']:
                                code = result.get('code', '') or result.get('input', {}).get('code', '')
                                outputs = result.get('outputs')
                                if code:
                                    tool_msg += f" - Code: {code[:50]}{'...' if len(code) > 50 else ''}"
                                if outputs:
                                    tool_msg += f" - Result: {outputs}"
                            elif tool_type == 'web_search':
                                query = result.get('query', '') or result.get('input', {}).get('query', '')
                                if query:
                                    tool_msg += f" - Query: '{query}'"
                            
                            # Display as tool content for the specific agent
                            await self._process_agent_content(source, tool_msg)
                    continue
                
                if content:
                    full_response += content
                    
                    # Log chunk
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk.type)
                    
                    # Process content by source
                    await self._process_content(source, content)
            
            # Display vote results and get final presentation
            status = orchestrator.get_status()
            vote_results = status.get('vote_results', {})
            selected_agent = status.get('selected_agent')
            
            if vote_results.get('vote_counts'):
                self._display_vote_results(vote_results)
                # Allow time for voting results to be visible
                import time
                time.sleep(1.0)
            
            # Get final presentation from winning agent
            if self.enable_final_presentation and selected_agent and vote_results.get('vote_counts'):
                print(f"\n🎤  Final Presentation from {selected_agent}:")
                print("=" * 60)
                
                presentation_content = ""
                try:
                    async for chunk in orchestrator.get_final_presentation(selected_agent, vote_results):
                        content = getattr(chunk, 'content', '') or ''
                        if content:
                            # Ensure content is a string
                            if isinstance(content, list):
                                content = ' '.join(str(item) for item in content)
                            elif not isinstance(content, str):
                                content = str(content)
                            
                            # Simple content accumulation - let the display handle formatting
                            presentation_content += content
                            
                            # Log presentation chunk
                            if self.logger:
                                self.logger.log_chunk(selected_agent, content, getattr(chunk, 'type', 'presentation'))
                            
                            # Display the presentation in real-time
                            if self.display:
                                try:
                                    await self._process_content(selected_agent, content)
                                except Exception as e:
                                    # Error processing presentation content - continue gracefully
                                    pass
                            else:
                                # Simple print for non-display mode
                                print(content, end='', flush=True)
                except AttributeError:
                    # get_final_presentation method doesn't exist or failed
                    print("Final presentation not available - using coordination result")
                    presentation_content = ""
                
                final_answer = presentation_content
                print("\n" + "=" * 60)
                # Allow time for final presentation to be fully visible
                time.sleep(1.5)
            
            # Get the clean final answer from orchestrator's stored state (avoids token spacing issues)
            orchestrator_final_answer = None
            if selected_agent and hasattr(orchestrator, 'agent_states') and selected_agent in orchestrator.agent_states:
                stored_answer = orchestrator.agent_states[selected_agent].answer
                if stored_answer:
                    # Clean up the stored answer
                    orchestrator_final_answer = stored_answer.replace('\\', '\n').replace('**', '').strip()
            
            # Use orchestrator's clean answer if available, otherwise fall back to presentation
            final_result = orchestrator_final_answer if orchestrator_final_answer else (final_answer if final_answer else full_response)
            if final_result:
                print(f"\n🎯 FINAL COORDINATED ANSWER")
                print("=" * 80)
                print(f"{final_result.strip()}")
                print("=" * 80)
                
                # Show which agent was selected
                if selected_agent:
                    print(f"✅ Selected by: {selected_agent}")
                    if vote_results.get('vote_counts'):
                        vote_summary = ", ".join([f"{agent}: {count}" for agent, count in vote_results['vote_counts'].items()])
                        print(f"🗳️ Vote results: {vote_summary}")
                print()
            
            # Finalize session
            if self.logger:
                session_info = self.logger.finalize_session(final_answer, success=True)
                print(f"💾 Session log: {session_info['filename']}")
                print(f"⏱️  Duration: {session_info['duration']:.1f}s | Chunks: {session_info['total_chunks']} | Events: {session_info['orchestrator_events']}")
            
            return final_result
            
        except Exception as e:
            if self.logger:
                self.logger.finalize_session("", success=False)
            raise
        finally:
            if self.display:
                self.display.cleanup()
    
    async def coordinate_with_context(self, orchestrator, question: str, messages: List[Dict[str, Any]], agent_ids: Optional[List[str]] = None) -> str:
        """Coordinate agents with conversation context and visual display.
        
        Args:
            orchestrator: MassGen orchestrator instance
            question: Current question for coordination
            messages: Full conversation message history
            agent_ids: Optional list of agent IDs (auto-detected if not provided)
            
        Returns:
            Final coordinated response
        """
        self.orchestrator = orchestrator
        
        # Auto-detect agent IDs if not provided
        if agent_ids is None:
            self.agent_ids = list(orchestrator.agents.keys())
        else:
            self.agent_ids = agent_ids
        
        # Initialize display if not provided
        if self.display is None:
            if self.display_type == "terminal":
                self.display = TerminalDisplay(self.agent_ids, **self.config)
            elif self.display_type == "simple":
                self.display = SimpleDisplay(self.agent_ids, **self.config)
            elif self.display_type == "rich_terminal":
                if not is_rich_available():
                    print("⚠️  Rich library not available. Falling back to terminal display.")
                    print("   Install with: pip install rich")
                    self.display = TerminalDisplay(self.agent_ids, **self.config)
                else:
                    self.display = RichTerminalDisplay(self.agent_ids, **self.config)
            else:
                raise ValueError(f"Unknown display type: {self.display_type}")
        
        # Pass orchestrator reference to display for backend info
        self.display.orchestrator = orchestrator
        
        # Initialize logger and display with context info
        log_filename = None
        if self.logger:
            # Add context info to session initialization
            context_info = f"(with {len(messages)//2} previous exchanges)" if len(messages) > 1 else ""
            session_question = f"{question} {context_info}"
            log_filename = self.logger.initialize_session(session_question, self.agent_ids)
            monitoring = self.logger.get_monitoring_commands()
            print(f"📁 Real-time log: {log_filename}")
            print(f"💡 Monitor with: {monitoring['tail']}")
            print()
        
        self.display.initialize(question, log_filename)
        
        try:
            # Process coordination stream with conversation context
            full_response = ""
            final_answer = ""
            
            # Use the orchestrator's chat method with full message context
            async for chunk in orchestrator.chat(messages):
                content = getattr(chunk, 'content', '') or ''
                source = getattr(chunk, 'source', None)
                chunk_type = getattr(chunk, 'type', '')
                
                # Handle agent status updates
                if chunk_type == "agent_status":
                    status = getattr(chunk, 'status', None)
                    if source and status:
                        self.display.update_agent_status(source, status)
                    continue

                # Handle builtin tool results  
                elif chunk_type == "builtin_tool_results":
                    builtin_results = getattr(chunk, 'builtin_tool_results', [])
                    if builtin_results and source:
                        for result in builtin_results:
                            tool_type = result.get('tool_type', 'unknown')
                            status_result = result.get('status', 'unknown')
                            tool_msg = f"🔧 [{tool_type.title()}] {status_result.title()}"
                            
                            if tool_type in ['code_interpreter', 'code_execution']:
                                code = result.get('code', '') or result.get('input', {}).get('code', '')
                                outputs = result.get('outputs')
                                if code:
                                    tool_msg += f" - Code: {code[:50]}{'...' if len(code) > 50 else ''}"
                                if outputs:
                                    tool_msg += f" - Result: {outputs}"
                            elif tool_type == 'web_search':
                                query = result.get('query', '') or result.get('input', {}).get('query', '')
                                if query:
                                    tool_msg += f" - Query: '{query}'"
                            
                            # Display as tool content for the specific agent
                            await self._process_agent_content(source, tool_msg)
                    continue
                
                if content:
                    full_response += content
                    
                    # Log chunk
                    if self.logger:
                        self.logger.log_chunk(source, content, chunk.type)
                    
                    # Process content by source
                    await self._process_content(source, content)
            
            # Display vote results and get final presentation
            status = orchestrator.get_status()
            vote_results = status.get('vote_results', {})
            selected_agent = status.get('selected_agent')
            
            if vote_results.get('vote_counts'):
                self._display_vote_results(vote_results)
                # Allow time for voting results to be visible
                import time
                time.sleep(1.0)
            
            # Get final presentation from winning agent
            if self.enable_final_presentation and selected_agent and vote_results.get('vote_counts'):
                print(f"\n🎤 Final Presentation from {selected_agent}:")
                print("=" * 60)
                
                presentation_content = ""
                try:
                    async for chunk in orchestrator.get_final_presentation(selected_agent, vote_results):
                        content = getattr(chunk, 'content', '') or ''
                        if content:
                            # Ensure content is a string
                            if isinstance(content, list):
                                content = ' '.join(str(item) for item in content)
                            elif not isinstance(content, str):
                                content = str(content)
                            
                            # Simple content accumulation - let the display handle formatting
                            presentation_content += content
                            
                            # Log presentation chunk
                            if self.logger:
                                self.logger.log_chunk(selected_agent, content, getattr(chunk, 'type', 'presentation'))
                            
                            # Stream presentation to console
                            print(content, end='', flush=True)
                            
                            # Update display
                            await self._process_content(selected_agent, content)
                            
                            if getattr(chunk, 'type', '') == 'done':
                                break
                                
                except Exception as e:
                    print(f"\n❌ Error during final presentation: {e}")
                    presentation_content = full_response  # Fallback
                
                final_answer = presentation_content
                print("\n" + "=" * 60)
                # Allow time for final presentation to be fully visible
                time.sleep(1.5)
            
            # Get the clean final answer from orchestrator's stored state
            orchestrator_final_answer = None
            if selected_agent and hasattr(orchestrator, 'agent_states') and selected_agent in orchestrator.agent_states:
                stored_answer = orchestrator.agent_states[selected_agent].answer
                if stored_answer:
                    # Clean up the stored answer
                    orchestrator_final_answer = stored_answer.replace('\\', '\n').replace('**', '').strip()
            
            # Use orchestrator's clean answer if available, otherwise fall back to presentation
            final_result = orchestrator_final_answer if orchestrator_final_answer else (final_answer if final_answer else full_response)
            if final_result:
                print(f"\n🎯 FINAL COORDINATED ANSWER")
                print("=" * 80)
                print(f"{final_result.strip()}")
                print("=" * 80)
                
                # Show which agent was selected
                if selected_agent:
                    print(f"✅ Selected by: {selected_agent}")
                    if vote_results.get('vote_counts'):
                        vote_summary = ", ".join([f"{agent}: {count}" for agent, count in vote_results['vote_counts'].items()])
                        print(f"🗳️ Vote results: {vote_summary}")
                print()
            
            # Finalize session
            if self.logger:
                session_info = self.logger.finalize_session(final_answer, success=True)
                print(f"💾 Session log: {session_info['filename']}")
                print(f"⏱️  Duration: {session_info['duration']:.1f}s | Chunks: {session_info['total_chunks']} | Events: {session_info['orchestrator_events']}")
            
            return final_result
            
        except Exception as e:
            if self.logger:
                self.logger.finalize_session("", success=False)
            raise
        finally:
            if self.display:
                self.display.cleanup()
    
    def _display_vote_results(self, vote_results: Dict[str, Any]):
        """Display voting results in a formatted table."""
        print(f"\n🗳️  VOTING RESULTS")
        print("=" * 50)
        
        vote_counts = vote_results.get('vote_counts', {})
        voter_details = vote_results.get('voter_details', {})
        winner = vote_results.get('winner')
        is_tie = vote_results.get('is_tie', False)
        
        # Display vote counts
        if vote_counts:
            print(f"\n📊 Vote Count:")
            for agent_id, count in sorted(vote_counts.items(), key=lambda x: x[1], reverse=True):
                winner_mark = "🏆" if agent_id == winner else "  "
                tie_mark = " (tie-broken)" if is_tie and agent_id == winner else ""
                print(f"   {winner_mark} {agent_id}: {count} vote{'s' if count != 1 else ''}{tie_mark}")
        
        # Display voter details
        if voter_details:
            print(f"\n🔍 Vote Details:")
            for voted_for, voters in voter_details.items():
                print(f"   → {voted_for}:")
                for voter_info in voters:
                    voter = voter_info['voter']
                    reason = voter_info['reason']
                    print(f"     • {voter}: \"{reason}\"")
        
        # Display tie-breaking info
        if is_tie:
            print(f"\n⚖️  Tie broken by agent registration order (orchestrator setup order)")
        
        # Display summary stats
        total_votes = vote_results.get('total_votes', 0)
        agents_voted = vote_results.get('agents_voted', 0)
        print(f"\n📈 Summary: {agents_voted}/{total_votes} agents voted")
        print("=" * 50)
    
    async def _process_content(self, source: Optional[str], content: str):
        """Process content from coordination stream."""
        # Handle agent content
        if source in self.agent_ids:
            await self._process_agent_content(source, content)
        
        # Handle orchestrator content  
        elif source in ["coordination_hub", "orchestrator"] or source is None:
            await self._process_orchestrator_content(content)
        
        # Capture coordination events from any source (orchestrator or agents)
        if any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]):
            clean_line = content.replace('**', '').replace('##', '').strip()
            if clean_line and not any(skip in clean_line for skip in ["result ignored", "Starting", "Agents Coordinating", "Coordinating agents, please wait"]):
                event = f"🔄 {source}: {clean_line}" if source and source not in ["coordination_hub", "orchestrator"] else f"🔄 {clean_line}"
                self.display.add_orchestrator_event(event)
                if self.logger:
                    self.logger.log_orchestrator_event(event)
    
    async def _process_agent_content(self, agent_id: str, content: str):
        """Process content from a specific agent."""
        # Update agent status - if agent is streaming content, they're working
        # But don't override "completed" status
        current_status = self.display.get_agent_status(agent_id)
        if current_status not in ["working", "completed"]:
            self.display.update_agent_status(agent_id, "working")
        
        # Determine content type and process
        if "🔧" in content or "🔄 Vote invalid" in content:
            # Tool usage or status messages
            content_type = "tool" if "🔧" in content else "status"
            self.display.update_agent_content(agent_id, content, content_type)
            
            # Update status on completion
            if "new_answer" in content or "vote" in content:
                self.display.update_agent_status(agent_id, "completed")
            
            # Log to detailed logger
            if self.logger:
                self.logger.log_agent_content(agent_id, content, content_type)
        
        else:
            # Thinking content
            self.display.update_agent_content(agent_id, content, "thinking")
            if self.logger:
                self.logger.log_agent_content(agent_id, content, "thinking")
    
    async def _process_orchestrator_content(self, content: str):
        """Process content from orchestrator."""
        # Handle final answer - merge with voting info
        if "Final Coordinated Answer" in content:
            # Don't create event yet - wait for actual answer content to merge
            pass
        
        # Handle coordination events (provided answer, votes)
        elif any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]):
            clean_line = content.replace('**', '').replace('##', '').strip()
            if clean_line and not any(skip in clean_line for skip in ["result ignored", "Starting", "Agents Coordinating", "Coordinating agents, please wait"]):
                event = f"🔄 {clean_line}"
                self.display.add_orchestrator_event(event)
                if self.logger:
                    self.logger.log_orchestrator_event(event)
        
        # Handle final answer content - create merged event with voting info
        elif ("Final Coordinated Answer" not in content and 
              not any(marker in content for marker in ["✅", "🗳️", "🎯", "Starting", "Agents Coordinating", "🔄", "**", "result ignored", "restart pending"])):
            # Extract clean final answer content
            clean_content = content.strip()
            if clean_content and not clean_content.startswith('---') and not clean_content.startswith('*Coordinated by'):
                # Get orchestrator status for voting results and winner
                status = self.orchestrator.get_status()
                selected_agent = status.get('selected_agent', 'Unknown')
                vote_results = status.get('vote_results', {})
                vote_counts = vote_results.get('vote_counts', {})
                is_tie = vote_results.get('is_tie', False)
                
                # Create comprehensive final event
                if vote_counts:
                    vote_summary = ", ".join([f"{agent}: {count} vote{'s' if count != 1 else ''}" for agent, count in vote_counts.items()])
                    tie_info = " (tie-broken by registration order)" if is_tie else ""
                    event = f"🎯 FINAL: {selected_agent} selected ({vote_summary}{tie_info}) → {clean_content}"
                else:
                    event = f"🎯 FINAL: {selected_agent} selected → {clean_content}"
                
                self.display.add_orchestrator_event(event)
                if self.logger:
                    self.logger.log_orchestrator_event(event)
                
                import asyncio
                await asyncio.sleep(1.5) 
                
                if hasattr(self.display, '_update_display'):
                    self.display._update_display(force=True)
                    await asyncio.sleep(0.3) 
                
                self.display.show_final_answer(clean_content)


# Convenience functions for common use cases
async def coordinate_with_terminal_ui(orchestrator, question: str, enable_final_presentation: bool = True, **kwargs) -> str:
    """Quick coordination with terminal UI and logging.
    
    Args:
        orchestrator: MassGen orchestrator instance
        question: Question for coordination
        enable_final_presentation: Whether to ask winning agent to present final answer
        **kwargs: Additional configuration
        
    Returns:
        Final coordinated response
    """
    ui = CoordinationUI(display_type="terminal", enable_final_presentation=enable_final_presentation, **kwargs)
    return await ui.coordinate(orchestrator, question)


async def coordinate_with_simple_ui(orchestrator, question: str, enable_final_presentation: bool = True, **kwargs) -> str:
    """Quick coordination with simple UI and logging.
    
    Args:
        orchestrator: MassGen orchestrator instance  
        question: Question for coordination
        **kwargs: Additional configuration
        
    Returns:
        Final coordinated response
    """
    ui = CoordinationUI(display_type="simple", enable_final_presentation=enable_final_presentation, **kwargs)
    return await ui.coordinate(orchestrator, question)


async def coordinate_with_rich_ui(orchestrator, question: str, enable_final_presentation: bool = True, **kwargs) -> str:
    """Quick coordination with rich terminal UI and logging.
    
    Args:
        orchestrator: MassGen orchestrator instance
        question: Question for coordination
        enable_final_presentation: Whether to ask winning agent to present final answer
        **kwargs: Additional configuration (theme, refresh_rate, etc.)
        
    Returns:
        Final coordinated response
    """
    ui = CoordinationUI(display_type="rich_terminal", enable_final_presentation=enable_final_presentation, **kwargs)
    return await ui.coordinate(orchestrator, question)