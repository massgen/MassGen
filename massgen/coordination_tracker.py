"""
Coordination Tracker for MassGen Orchestrator

This module provides comprehensive tracking of agent coordination events,
state transitions, and context sharing. It's integrated into the orchestrator
to capture the complete coordination flow for visualization and analysis.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

class EventType(Enum):
    """Types of coordination events."""
    # Orchestrator events
    COORDINATION_START = "coordination_start"
    COORDINATION_END = "coordination_end"
    
    # Agent lifecycle events
    AGENT_START = "agent_start"
    AGENT_RESTART = "agent_restart"
    AGENT_COMPLETE = "agent_complete"
    AGENT_IDLE = "agent_idle"
    AGENT_TIMEOUT = "agent_timeout"
    
    # Agent action events
    AGENT_ANSWERING = "agent_answering"
    AGENT_VOTING = "agent_voting"
    AGENT_NEW_ANSWER = "agent_new_answer"
    AGENT_VOTE_CAST = "agent_vote_cast"
    
    # Context events
    CONTEXT_SHARED = "context_shared"
    CONTEXT_RECEIVED = "context_received"
    CONTEXT_SNAPSHOT = "context_snapshot"
    
    # System events
    RESTART_TRIGGERED = "restart_triggered"
    CONSENSUS_REACHED = "consensus_reached"
    TIMEOUT_TRIGGERED = "timeout_triggered"

class AgentStatus(Enum):
    """Current status of an agent."""
    IDLE = "idle"  # waiting for other tasks
    ANSWERING = "answering"
    VOTING = "voting"
    RESTARTING = "restarting"
    COMPLETED = "completed"
    TIMEOUT = "timeout"

@dataclass
class CoordinationEvent:
    """Represents a single event in the coordination process."""
    timestamp: float
    event_type: EventType
    agent_id: Optional[str] = None
    details: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Ensure timestamp is set."""
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "agent_id": self.agent_id,
            "details": self.details,
            "context": self.context
        }

@dataclass
class AgentCoordinationState:
    """Tracks the coordination state for a single agent."""
    agent_id: str
    status: AgentStatus = AgentStatus.IDLE
    events: List[CoordinationEvent] = field(default_factory=list)
    
    # Coordination stats
    answer_count: int = 0
    vote_count: int = 0
    restart_count: int = 0
    
    # Current state
    current_answer: Optional[str] = None
    current_vote: Optional[Dict[str, str]] = None
    has_voted: bool = False
    has_answered: bool = False
    
    # Answer versioning (agent_id.answer_num format like agent1.1, agent1.2)
    answers_provided: List[Dict[str, Any]] = field(default_factory=list)
    
    # Context tracking - what the agent sees when it starts
    context_version: int = 0
    context_received_from: List[str] = field(default_factory=list)
    context_answers: Dict[str, str] = field(default_factory=dict)  # Answers agent can see
    conversation_context: Optional[Dict[str, Any]] = None  # Full conversation context
    
    # Timing
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    total_active_time: float = 0.0
    
    def add_event(self, event: CoordinationEvent):
        """Add an event to this agent's timeline."""
        self.events.append(event)
        
        # Update status based on event type
        if event.event_type == EventType.AGENT_START:
            self.status = AgentStatus.ANSWERING
            if self.start_time is None:
                self.start_time = event.timestamp
        elif event.event_type == EventType.AGENT_ANSWERING:
            self.status = AgentStatus.ANSWERING
        elif event.event_type == EventType.AGENT_VOTING:
            self.status = AgentStatus.VOTING
        elif event.event_type == EventType.AGENT_NEW_ANSWER:
            self.status = AgentStatus.IDLE
            self.answer_count += 1
            self.has_answered = True
            self.current_answer = event.details
        elif event.event_type == EventType.AGENT_VOTE_CAST:
            self.status = AgentStatus.IDLE
            self.vote_count += 1
            self.has_voted = True
            if event.context:
                self.current_vote = event.context
        elif event.event_type == EventType.AGENT_RESTART:
            self.status = AgentStatus.RESTARTING
            self.restart_count += 1
            self.has_voted = False  # Reset on restart
        elif event.event_type == EventType.AGENT_IDLE:
            self.status = AgentStatus.IDLE
        elif event.event_type == EventType.AGENT_COMPLETE:
            self.status = AgentStatus.COMPLETED
            self.end_time = event.timestamp
        elif event.event_type == EventType.AGENT_TIMEOUT:
            self.status = AgentStatus.TIMEOUT
            self.end_time = event.timestamp
    
    def get_active_time(self) -> float:
        """Calculate total active time for this agent."""
        if not self.events:
            return 0.0
        
        active_time = 0.0
        work_start = None
        
        for event in self.events:
            if event.event_type in [EventType.AGENT_START, EventType.AGENT_RESTART]:
                work_start = event.timestamp
            elif event.event_type in [EventType.AGENT_IDLE, EventType.AGENT_COMPLETE, 
                                    EventType.AGENT_TIMEOUT] and work_start:
                active_time += event.timestamp - work_start
                work_start = None
        
        # If still working, add time until now
        if work_start:
            active_time += time.time() - work_start
        
        return active_time

@dataclass
class CoordinationTracker:
    """
    Tracks the complete coordination process for analysis and visualization.
    
    This is integrated into the Orchestrator to capture all coordination events,
    agent states, and context sharing information.
    """
    
    # Agent states
    agent_states: Dict[str, AgentCoordinationState] = field(default_factory=dict)
    
    # Global events timeline
    global_events: List[CoordinationEvent] = field(default_factory=list)
    
    # Context tracking
    context_versions: Dict[str, int] = field(default_factory=dict)
    context_snapshots: List[Tuple[float, Dict[str, str]]] = field(default_factory=list)
    
    # Coordination stats
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    total_rounds: int = 0
    total_restarts: int = 0
    
    # Consensus tracking
    final_winner: Optional[str] = None
    final_votes: Dict[str, str] = field(default_factory=dict)
    consensus_reached: bool = False
    
    def initialize_agents(self, agent_ids: List[str]):
        """Initialize tracking for a set of agents."""
        self.start_time = time.time()
        for agent_id in agent_ids:
            self.agent_states[agent_id] = AgentCoordinationState(agent_id)
            self.add_event(EventType.AGENT_IDLE, agent_id, "Initialized")
    
    def add_event(self, event_type: EventType, agent_id: Optional[str] = None, 
                  details: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        """Add a coordination event."""
        event = CoordinationEvent(
            timestamp=time.time(),
            event_type=event_type,
            agent_id=agent_id,
            details=details,
            context=context
        )
        
        # Add to global timeline
        self.global_events.append(event)
        
        # Add to agent-specific timeline if applicable
        if agent_id and agent_id in self.agent_states:
            self.agent_states[agent_id].add_event(event)
        
        # Handle special event types
        if event_type == EventType.AGENT_NEW_ANSWER:
            self._handle_new_answer(agent_id)
        elif event_type == EventType.RESTART_TRIGGERED:
            self.total_restarts += 1
        elif event_type == EventType.CONSENSUS_REACHED:
            self.consensus_reached = True
            self.end_time = time.time()
    
    def _handle_new_answer(self, answering_agent: str):
        """Handle context sharing when a new answer is provided."""
        # Increment global context version
        version = self.context_versions.get("global", 0) + 1
        self.context_versions["global"] = version
        
        # Record context snapshot
        current_answers = {
            aid: state.current_answer 
            for aid, state in self.agent_states.items() 
            if state.current_answer
        }
        self.context_snapshots.append((time.time(), current_answers))
        
        # Mark context as shared
        self.add_event(EventType.CONTEXT_SHARED, answering_agent, 
                      f"Context v{version} shared")
        
        # Mark other agents as receiving new context
        for aid in self.agent_states.keys():
            if aid != answering_agent:
                self.agent_states[aid].context_version = version
                self.agent_states[aid].context_received_from.append(answering_agent)
                self.add_event(EventType.CONTEXT_RECEIVED, aid,
                              f"Received context v{version} from {answering_agent}")
    
    def track_agent_start(self, agent_id: str, existing_answers: Dict[str, str], 
                          conversation_context: Optional[Dict[str, Any]] = None):
        """Track when an agent starts or restarts."""
        is_restart = self.agent_states[agent_id].restart_count > 0
        event_type = EventType.AGENT_RESTART if is_restart else EventType.AGENT_START
        
        # Store full context information
        self.agent_states[agent_id].context_answers = existing_answers.copy()
        self.agent_states[agent_id].conversation_context = conversation_context
        
        # Create context mapping with answer labels (agent1.1, agent2.1, etc.)
        answer_labels = {}
        for i, (aid, answer) in enumerate(existing_answers.items(), 1):
            agent_num = list(self.agent_states.keys()).index(aid) + 1
            answer_num = len([a for a in self.agent_states[aid].answers_provided]) or 1
            answer_labels[f"agent{agent_num}.{answer_num}"] = {
                "agent_id": aid,
                "content": answer,
                "preview": answer[:50] + "..." if len(answer) > 50 else answer
            }
        
        context_info = {
            "existing_answers": list(existing_answers.keys()),
            "context_version": self.context_versions.get("global", 0),
            "answer_labels": answer_labels,
            "has_conversation_history": bool(conversation_context and conversation_context.get("conversation_history"))
        }
        
        self.add_event(event_type, agent_id, 
                      f"Started with {len(existing_answers)} answers",
                      context_info)
    
    def track_vote(self, agent_id: str, voted_for: str, reason: str):
        """Track when an agent votes."""
        # Get the answer being voted for
        voted_for_agent_state = self.agent_states.get(voted_for)
        voted_answer = None
        answer_label = None
        
        if voted_for_agent_state and voted_for_agent_state.current_answer:
            voted_answer = voted_for_agent_state.current_answer
            # Create answer label (agent1.1, agent2.1, etc.)
            agent_num = list(self.agent_states.keys()).index(voted_for) + 1
            answer_num = len(voted_for_agent_state.answers_provided)
            answer_label = f"agent{agent_num}.{answer_num}"
        
        # Convert available agent IDs to answer labels
        available_answer_labels = []
        for context_agent_id in self.agent_states[agent_id].context_answers.keys():
            context_agent_num = list(self.agent_states.keys()).index(context_agent_id) + 1
            # Assume latest answer (could be improved to track specific answer versions)
            available_answer_labels.append(f"agent{context_agent_num}.1")
        
        vote_context = {
            "voted_for": voted_for,
            "reason": reason,
            "answer_label": answer_label,
            "voted_answer": voted_answer,
            "available_answers": available_answer_labels
        }
        
        self.add_event(EventType.AGENT_VOTE_CAST, agent_id,
                      f"Voted for {answer_label or voted_for}: {reason[:30]}...",
                      vote_context)
        self.final_votes[agent_id] = voted_for
    
    def track_new_answer(self, agent_id: str, answer: str):
        """Track when an agent provides a new answer."""
        # Create answer version tracking
        agent_state = self.agent_states[agent_id]
        answer_num = len(agent_state.answers_provided) + 1
        agent_num = list(self.agent_states.keys()).index(agent_id) + 1
        answer_label = f"agent{agent_num}.{answer_num}"
        
        # Store full answer with metadata
        answer_record = {
            "answer_num": answer_num,
            "content": answer,
            "timestamp": time.time(),
            "label": answer_label
        }
        agent_state.answers_provided.append(answer_record)
        agent_state.current_answer = answer
        
        # Track the event with answer label
        display_preview = answer[:80] + "..." if len(answer) > 80 else answer
        self.add_event(EventType.AGENT_NEW_ANSWER, agent_id, 
                      f"Answer {answer_label}: {display_preview}",
                      {"answer_label": answer_label, "full_answer": answer})
    
    def track_restart_signal(self, triggering_agent: str, agents_restarted: List[str]):
        """Track when a restart is triggered, both who restarted it and who is affected."""
        self.add_event(EventType.RESTART_TRIGGERED, triggering_agent,
                       "Triggered global restart", context={"affected_agents": agents_restarted})
        for agent_id in agents_restarted:
            self.add_event(EventType.AGENT_RESTART, agent_id,
                          f"Restarting due to {triggering_agent}'s trigger")

    def set_final_winner(self, agent_id: str):
        """Set the final winning agent."""
        self.final_winner = agent_id
        self.add_event(EventType.CONSENSUS_REACHED, agent_id,
                      "Selected as final presenter")
    
    def track_final_answer(self, agent_id: str, final_answer: str):
        """Track the final answer presentation (agentX.final)."""
        agent_num = list(self.agent_states.keys()).index(agent_id) + 1
        final_label = f"agent{agent_num}.final"
        
        # Store final answer
        final_record = {
            "answer_num": "final",
            "content": final_answer,
            "timestamp": time.time(),
            "label": final_label
        }
        self.agent_states[agent_id].answers_provided.append(final_record)
        
        # Track the event
        display_preview = final_answer[:80] + "..." if len(final_answer) > 80 else final_answer
        self.add_event(EventType.AGENT_NEW_ANSWER, agent_id,
                      f"Final answer {final_label}: {display_preview}",
                      {"answer_label": final_label, "full_answer": final_answer, "is_final": True})
    
    def track_agent_error(self, agent_id: str, error_message: str):
        """Track when an agent encounters an error."""
        self.add_event(EventType.AGENT_TIMEOUT, agent_id, 
                      f"Agent error: {error_message[:100]}...",
                      {"error": error_message, "error_type": "agent_error"})
        
        # Update agent status
        if agent_id in self.agent_states:
            self.agent_states[agent_id].status = AgentStatus.TIMEOUT
    
    def track_agent_terminated(self, agent_id: str):
        """Track when an agent is terminated/killed."""
        self.add_event(EventType.AGENT_COMPLETE, agent_id, 
                      "Agent terminated/killed")
        
        # Update agent status  
        if agent_id in self.agent_states:
            self.agent_states[agent_id].status = AgentStatus.COMPLETED
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a comprehensive summary of the coordination process."""
        duration = (self.end_time or time.time()) - (self.start_time or 0)
        
        # Calculate per-agent stats
        agent_stats = {}
        for aid, state in self.agent_states.items():
            agent_stats[aid] = {
                "status": state.status.value,
                "answer_count": state.answer_count,
                "vote_count": state.vote_count,
                "restart_count": state.restart_count,
                "active_time": state.get_active_time(),
                "events_count": len(state.events),
                "final_vote": state.current_vote,
                "has_answer": state.has_answered
            }
        
        return {
            "duration": duration,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_events": len(self.global_events),
            "total_restarts": self.total_restarts,
            "context_versions": self.context_versions.get("global", 0),
            "consensus_reached": self.consensus_reached,
            "final_winner": self.final_winner,
            "final_votes": self.final_votes,
            "agent_stats": agent_stats,
            "context_snapshots_count": len(self.context_snapshots)
        }
    
    def get_timeline(self) -> List[Dict[str, Any]]:
        """Get the complete event timeline."""
        return [event.to_dict() for event in self.global_events]
    
    def get_agent_timeline(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get timeline for a specific agent."""
        if agent_id not in self.agent_states:
            return []
        return [event.to_dict() for event in self.agent_states[agent_id].events]
    
    def save_coordination_logs(self, log_dir):
        """Save comprehensive coordination logs and visualizations."""
        from .logger_config import logger
        
        try:
            # Save raw event logs
            import json
            
            # Global events log
            global_events_file = log_dir / "raw_events_global.json"
            with open(global_events_file, 'w', encoding='utf-8') as ef:
                global_events = self.get_timeline()
                json.dump(global_events, ef, indent=2, default=str)
            
            # Per-agent events
            for agent_id in self.agent_states.keys():
                agent_events = self.get_agent_timeline(agent_id)
                if agent_events:
                    agent_events_file = log_dir / f"raw_events_{agent_id}.json"
                    with open(agent_events_file, 'w', encoding='utf-8') as ef:
                        json.dump(agent_events, ef, indent=2, default=str)
            
            # Create Rich-formatted timeline summary
            self._create_rich_timeline_summary(log_dir)
            
            # Save individual answer files
            self._save_answer_files(log_dir)
            
            logger.info(f"Coordination logs saved to: {log_dir}")
            
        except Exception as e:
            logger.warning(f"Failed to save coordination logs: {e}")
    
    def _create_rich_timeline_summary(self, log_dir):
        """Create a principled Rich-formatted timeline based on events."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich.columns import Columns
            from rich import box
            import io
            
            # Generate timeline from events - purely event-driven
            timeline_steps = self._generate_timeline_from_events()
            agent_ids = list(self.agent_states.keys())
            summary = self.get_summary()
            
            # Create console that captures to string (without colors for file)
            console_output = io.StringIO()
            file_console = Console(file=console_output, width=120, force_terminal=False, color_system=None)
            
            # Create file output
            file_console.print("=" * 120)
            file_console.print("MASSGEN COORDINATION SUMMARY")
            file_console.print("=" * 120)
            file_console.print()
            
            # Description
            file_console.print("DESCRIPTION:")
            file_console.print("This timeline shows the coordination flow between multiple AI agents.")
            file_console.print("• Context: Previous answers supplied to each agent as background")
            file_console.print("• User Query: The original task/question is always included in each agent's prompt")
            file_console.print("• Coordination: Agents build upon each other's work through answer sharing and voting")
            file_console.print()
            
            # Agent mapping
            file_console.print("AGENT MAPPING:")
            for i, agent_id in enumerate(agent_ids):
                file_console.print(f"  Agent{i+1} = {agent_id}")
            file_console.print()
            
            header_text = f"Duration: {summary['duration']:.1f}s | Events: {summary['total_events']} | Restarts: {summary['total_restarts']} | Winner: {summary['final_winner'] or 'None'}"
            file_console.print(header_text)
            file_console.print()
            
            # Create table for file (without colors)
            table = Table(box=box.ASCII, show_header=True)
            table.add_column("Step", width=6, justify="center")
            table.add_column("Event", width=30)
            
            for i, agent_id in enumerate(agent_ids):
                table.add_column(f"Agent{i+1}", width=40, justify="left")
            
            # Add rows from timeline steps
            for step in timeline_steps:
                row = [str(step["step"]), step["event"]]
                
                for agent_id in agent_ids:
                    agent_info = step["agents"].get(agent_id, {"status": "", "context": ""})
                    # Combine status and context with proper formatting
                    cell_content = agent_info['status']
                    if agent_info.get("context"):
                        cell_content += f"\n{agent_info['context']}"
                    row.append(cell_content)
                
                table.add_row(*row)
                # Add spacing between rows
                table.add_row(*["", "", *["" for _ in agent_ids]])
            
            file_console.print(table)
            file_console.print()
            
            # Key concepts for file
            file_console.print("KEY CONCEPTS:")
            file_console.print("-" * 20)
            file_console.print("• NEW ANSWER: Agent provides original response")
            file_console.print("• RESTART: Other agents discard work, restart with new context")
            file_console.print("• VOTING: Agents choose best answer from available options")
            file_console.print("• FINAL: Winning agent presents synthesized response") 
            file_console.print("• ERROR/TIMEOUT: Agent encounters issues")
            file_console.print()
            file_console.print("=" * 120)
            
            # Save file version
            timeline_file = log_dir / "coordination_timeline.txt" 
            with open(timeline_file, 'w', encoding='utf-8') as f:
                f.write(console_output.getvalue())
            
            # NOW PRINT the beautiful Rich version to terminal for immediate viewing
            terminal_console = Console(width=120, force_terminal=True)
            
            print("\n" + "="*120)
            print("📊 MASSGEN COORDINATION TIMELINE (Rich Preview)")
            print("="*120)
            
            # Beautiful terminal version with colors
            terminal_console.print()
            
            # Description panel
            description_text = """This timeline shows the coordination flow between multiple AI agents.
• [bold]Context:[/bold] Previous answers supplied to each agent as background
• [bold]User Query:[/bold] The original task/question is always included in each agent's prompt  
• [bold]Coordination:[/bold] Agents build upon each other's work through answer sharing and voting"""
            terminal_console.print(Panel(description_text, title="[bold green]Description[/bold green]", box=box.ROUNDED))
            
            # Agent mapping panel
            agent_mapping_text = "\n".join([f"Agent{i+1} = [cyan]{agent_id}[/cyan]" for i, agent_id in enumerate(agent_ids)])
            terminal_console.print(Panel(agent_mapping_text, title="[bold green]Agent Mapping[/bold green]", box=box.ROUNDED))
            
            terminal_console.print(Panel(header_text, title="[bold blue]MASSGEN COORDINATION SUMMARY[/bold blue]", box=box.DOUBLE))
            terminal_console.print()
            
            # Colorful table for terminal
            rich_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
            rich_table.add_column("Step", style="dim", width=6, justify="center")
            rich_table.add_column("Event", style="bold", width=30)
            
            for i, agent_id in enumerate(agent_ids):
                rich_table.add_column(f"Agent{i+1}", style="cyan", width=40, justify="left")
            
            # Add colorful rows
            for step in timeline_steps:
                row = [str(step["step"]), step["event"]]
                
                for agent_id in agent_ids:
                    agent_info = step["agents"].get(agent_id, {"status": "", "context": ""})
                    status = agent_info['status']
                    
                    # Add colors based on status type
                    if "NEW:" in status:
                        status_text = f"[bold green]{status}[/bold green]"
                    elif "VOTE:" in status:
                        status_text = f"[bold blue]{status}[/bold blue]"
                    elif "FINAL:" in status:
                        status_text = f"[bold purple]{status}[/bold purple]"
                    elif "RESTART" in status:
                        status_text = f"[bold yellow]{status}[/bold yellow]"
                    elif "ANSWERING" in status:
                        status_text = f"[bold cyan]{status}[/bold cyan]"
                    elif "VOTING" in status:
                        status_text = f"[bold blue]{status}[/bold blue]"
                    elif "SELECTED FOR FINAL PRESENTATION" in status:
                        status_text = f"[bold purple]{status}[/bold purple]"
                    elif "TERMINATED" in status:
                        status_text = f"[bold red]{status}[/bold red]"
                    else:
                        status_text = f"[dim]{status}[/dim]"
                    
                    # Add full context (not truncated)
                    if agent_info.get("context"):
                        status_text += f"\n[dim]{agent_info['context']}[/dim]"
                    
                    row.append(status_text)
                
                rich_table.add_row(*row)
                # Add some spacing between rows for clarity
                rich_table.add_row(*["", "", *["" for _ in agent_ids]])
            
            terminal_console.print(rich_table)
            terminal_console.print()
            
            # Colorful legend
            terminal_console.print(Panel(
                "[bold]KEY CONCEPTS:[/bold]\n"
                "• [green]NEW ANSWER[/green]: Agent provides original response\n" 
                "• [yellow]RESTART[/yellow]: Other agents discard work, restart with new context\n"
                "• [blue]VOTING[/blue]: Agents choose best answer from available options\n"
                "• [purple]FINAL[/purple]: Winning agent presents synthesized response\n"
                "• [red]ERROR/TIMEOUT[/red]: Agent encounters issues",
                title="[bold]Legend[/bold]",
                box=box.ROUNDED
            ))
            
            print("="*120)
            print(f"💾 Full timeline saved to: {timeline_file}")
            print("="*120 + "\n")
                
        except ImportError:
            # Fallback without Rich
            print("⚠️  Rich not available - using simple timeline format")
            self._create_simple_timeline_summary(log_dir)
        except Exception as e:
            from .logger_config import logger
            logger.warning(f"Failed to create Rich timeline: {e}")
            self._create_simple_timeline_summary(log_dir)
    
    def _generate_timeline_from_events(self):
        """Generate timeline steps purely from coordination events - no hardcoded logic."""
        timeline_steps = []
        step_num = 0
        agent_ids = list(self.agent_states.keys())
        
        # Track current agent states based on events
        context_available = {aid: [] for aid in agent_ids}
        current_status = {aid: "ANSWERING" for aid in agent_ids}  # Track each agent's current status
        
        # Step 0: Coordination start - all agents start answering
        timeline_steps.append({
            "step": step_num,
            "event": "COORDINATION START", 
            "agents": {aid: {"status": "ANSWERING", "context": "Context: []\nStarting to work on task"} for aid in agent_ids}
        })
        step_num += 1
        
        # Process global events chronologically  
        for event in self.global_events:
            event_type = event.event_type
            agent_id = event.agent_id
            
            if event_type == EventType.AGENT_NEW_ANSWER:
                # New answer event - derive everything from event context
                event_context = event.context or {}
                answer_label = event_context.get("answer_label", "unknown")
                is_final = event_context.get("is_final", False)
                full_answer = event_context.get("full_answer", "")
                
                if is_final:
                    # Final answer
                    preview = full_answer[:150] + "..." if len(full_answer) > 150 else full_answer
                    timeline_steps.append({
                        "step": step_num,
                        "event": f"FINAL ANSWER: {answer_label}",
                        "agents": {
                            aid: {
                                "status": f"FINAL: {answer_label}" if aid == agent_id else "TERMINATED",
                                "context": f"Context: {context_available[aid]}\nPreview: {preview}" if aid == agent_id else ""
                            } for aid in agent_ids
                        }
                    })
                    
                    # Update status - presenting agent does final, all others terminated
                    current_status[agent_id] = f"FINAL: {answer_label}"
                    for aid in agent_ids:
                        if aid != agent_id:
                            current_status[aid] = "TERMINATED"
                else:
                    # Regular answer
                    used_context = context_available[agent_id] if context_available[agent_id] else []
                    context_display = str(used_context) if used_context else "[]"
                    preview = full_answer[:150] + "..." if len(full_answer) > 150 else full_answer
                    
                    timeline_steps.append({
                        "step": step_num, 
                        "event": f"NEW ANSWER: {answer_label}",
                        "agents": {
                            aid: {
                                "status": f"NEW: {answer_label}" if aid == agent_id else current_status[aid],
                                "context": f"Context: {context_display}\nPreview: {preview}" if aid == agent_id 
                                           else f"Context: {str(context_available[aid]) if context_available[aid] else '[]'}\nWaiting for coordination to continue..."
                            } for aid in agent_ids
                        }
                    })
                    
                    # Update status and context
                    current_status[agent_id] = f"NEW: {answer_label}"
                    for aid in agent_ids:
                        # Agent who answered goes idle, others get new context
                        if aid == agent_id:
                            current_status[aid] = "idle"
                        if answer_label not in context_available[aid]:
                            context_available[aid].append(answer_label)
                
                step_num += 1
            
            elif event_type == EventType.RESTART_TRIGGERED:
                # Restart event - use agent alias instead of real ID
                triggering_agent_num = agent_ids.index(agent_id) + 1 if agent_id in agent_ids else 0
                affected_agents = event.context.get("affected_agents", []) if event.context else []
                timeline_steps.append({
                    "step": step_num,
                    "event": f"RESTART triggered by Agent{triggering_agent_num}",
                    "agents": {
                        aid: {
                            "status": "RESTART" if aid in affected_agents else ("idle" if aid == agent_id else current_status[aid]),
                            "context": f"Context: {context_available[aid]}\nPrevious work discarded, restarting with new context" if aid in affected_agents 
                                      else f"Context: {context_available[aid]}\nAnswer completed"
                        } for aid in agent_ids
                    }
                })
                
                # Update status - restarted agents go back to ANSWERING, triggering agent goes idle
                for aid in affected_agents:
                    current_status[aid] = "ANSWERING"
                current_status[agent_id] = "idle"  # Agent who triggered restart is now idle
                    
                step_num += 1
            
            elif event_type == EventType.AGENT_VOTE_CAST:
                # Check if this is part of a voting phase (multiple votes around same time)
                vote_context = event.context or {}
                voted_for = vote_context.get("answer_label", "unknown")
                reason = vote_context.get("reason", "")
                
                # Only add voting step if it's the first vote we see (others will be in same step)
                existing_vote_step = next((step for step in reversed(timeline_steps) if "VOTING PHASE" in step["event"]), None)
                
                if not existing_vote_step:
                    # Create new voting phase step
                    voting_agents = {}
                    for aid in agent_ids:
                        if aid == agent_id:
                            voting_agents[aid] = {
                                "status": f"VOTE: {voted_for}", 
                                "context": f"Selected: {voted_for}\nReasoning: {reason}"
                            }
                        else:
                            voting_agents[aid] = {
                                "status": "VOTING", 
                                "context": f"Context: {str(context_available[aid]) if context_available[aid] else '[]'}\nEvaluating available options..."
                            }
                    
                    timeline_steps.append({
                        "step": step_num,
                        "event": "VOTING PHASE (system-wide)",
                        "agents": voting_agents
                    })
                    
                    # Update status for all agents in voting phase
                    for aid in agent_ids:
                        if aid == agent_id:
                            current_status[aid] = f"VOTE: {voted_for}"
                        else:
                            current_status[aid] = "VOTING"
                            
                    step_num += 1
                else:
                    # Update existing voting step and status
                    existing_vote_step["agents"][agent_id] = {
                        "status": f"VOTE: {voted_for}",
                        "context": f"Selected: {voted_for}\nReasoning: {reason}"
                    }
                    current_status[agent_id] = f"VOTE: {voted_for}"
        
        # Add final agent selection step if we have a consensus reached event
        consensus_events = [e for e in self.global_events if e.event_type == EventType.CONSENSUS_REACHED]
        if consensus_events and not any("FINAL ANSWER:" in step["event"] for step in timeline_steps):
            # Get the winning agent
            winner_event = consensus_events[-1]  # Latest consensus
            winner_agent_id = winner_event.agent_id
            winner_agent_num = agent_ids.index(winner_agent_id) + 1 if winner_agent_id in agent_ids else 0
            
            timeline_steps.append({
                "step": step_num,
                "event": f"FINAL PRESENTER SELECTED: Agent{winner_agent_num}",
                "agents": {
                    aid: {
                        "status": f"SELECTED FOR FINAL PRESENTATION" if aid == winner_agent_id else "TERMINATED",
                        "context": f"Context: {context_available[aid]}\nChosen to present final synthesized answer" if aid == winner_agent_id 
                                  else f"Context: {context_available[aid]}\nCoordination complete, standing by"
                    } for aid in agent_ids
                }
            })
            
            # Update status
            for aid in agent_ids:
                if aid == winner_agent_id:
                    current_status[aid] = "SELECTED FOR FINAL PRESENTATION"
                else:
                    current_status[aid] = "TERMINATED"
                    
            step_num += 1
        
        return timeline_steps
    
    def _create_simple_timeline_summary(self, log_dir):
        """Fallback timeline without Rich."""
        summary_file = log_dir / "coordination_timeline.txt"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("MASSGEN COORDINATION TIMELINE\n")
            f.write("=" * 80 + "\n\n")
            
            summary = self.get_summary() 
            f.write(f"Duration: {summary['duration']:.1f}s | Events: {summary['total_events']} | Winner: {summary['final_winner']}\n\n")
            
            timeline_steps = self._generate_timeline_from_events()
            
            for step in timeline_steps:
                f.write(f"Step {step['step']}: {step['event']}\n")
                f.write("-" * 50 + "\n")
                
                agent_ids = list(self.agent_states.keys())
                for i, aid in enumerate(agent_ids):
                    agent_info = step["agents"].get(aid, {"status": "", "context": ""})
                    f.write(f"  Agent{i+1}: {agent_info['status']}\n")
                    if agent_info.get("context"):
                        f.write(f"            {agent_info['context']}\n")
                f.write("\n")
    
    def _save_answer_files(self, log_dir):
        """Save individual answer files."""
        agent_ids = list(self.agent_states.keys())
        
        for agent_id, state in self.agent_states.items():
            agent_num = agent_ids.index(agent_id) + 1
            for answer in state.answers_provided:
                if answer["answer_num"] == "final":
                    label = f"agent{agent_num}.final"
                else:
                    label = f"agent{agent_num}.{answer['answer_num']}"
                
                # Save individual answer file
                answer_file = log_dir / f"answer_{label}.txt"
                try:
                    with open(answer_file, 'w', encoding='utf-8') as af:
                        af.write(f"ANSWER: {label}\n")
                        af.write("=" * 50 + "\n")
                        af.write(f"Agent: {agent_id}\n")
                        af.write(f"Timestamp: {answer['timestamp']}\n")
                        af.write(f"Type: {'Final Answer' if answer['answer_num'] == 'final' else 'Regular Answer'}\n")
                        af.write("-" * 50 + "\n")
                        af.write(answer["content"])
                        af.write("\n")
                except Exception as e:
                    logger.warning(f"Failed to save answer file {label}: {e}")
