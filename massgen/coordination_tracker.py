"""
Coordination Tracker for MassGen Orchestrator

This module provides comprehensive tracking of agent coordination events,
state transitions, and context sharing. It's integrated into the orchestrator
to capture the complete coordination flow for visualization and analysis.

The new approach is principled: we simply record what happens as it happens,
without trying to infer or manage state transitions. The orchestrator tells
us exactly what occurred and when.
"""

import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from .utils import AgentStatus, ActionType

@dataclass
class CoordinationEvent:
    """A single coordination event with timestamp."""
    timestamp: float
    event_type: str
    agent_id: Optional[str] = None
    details: str = ""
    context: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "details": self.details,
            "context": self.context
        }

@dataclass 
class AgentAnswer:
    """Represents an answer from an agent."""
    agent_id: str
    content: str
    timestamp: float
    is_final: bool = False
    
    @property
    def label(self) -> str:
        """Auto-generate label based on answer properties."""
        # This will be set by the tracker when it knows agent order
        return getattr(self, '_label', 'unknown')
    
    @label.setter
    def label(self, value: str):
        self._label = value

@dataclass
class AgentVote:
    """Represents a vote from an agent."""
    voter_id: str
    voted_for: str  # Real agent ID like "gpt5nano_1"
    voted_for_label: str  # Answer label like "agent1.1"
    voter_anon_id: str  # Anonymous voter ID like "agent1"
    reason: str
    timestamp: float
    available_answers: List[str]  # Available answer labels like ["agent1.1", "agent2.1"]

class CoordinationTracker:
    """
    Principled coordination tracking that simply records what happens.
    
    The orchestrator tells us exactly what occurred and when, without
    us having to infer or manage complex state transitions.
    """
    
    def __init__(self):
        # Event log - chronological record of everything that happens
        self.events: List[CoordinationEvent] = []
        
        # Answer tracking with labeling
        self.answers_by_agent: Dict[str, List[AgentAnswer]] = {}  # agent_id -> list of answers
        self.all_answers: Dict[str, str] = {}  # label -> content mapping for easy lookup
        
        # Vote tracking
        self.votes: List[AgentVote] = []
        
        # Coordination iteration tracking
        self.current_iteration: int = 0
        self.current_round: int = 0  # Increments when restart triggered (new answer set)
        self.iteration_available_labels: List[str] = []  # Frozen snapshot of available answer labels for current iteration
        
        # Session info
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.agent_ids: List[str] = []
        self.final_winner: Optional[str] = None
        self.is_final_round: bool = False  # Track if we're in the final presentation round
        
        # Answer formatting settings
        self.preview_length = 150  # Default preview length for answers

    def initialize_session(self, agent_ids: List[str]):
        """Initialize a new coordination session."""
        self.start_time = time.time()
        self.agent_ids = agent_ids.copy()
        self.answers_by_agent = {aid: [] for aid in agent_ids}
        
        self._add_event("session_start", None, f"Started with agents: {agent_ids}")

    def start_new_iteration(self):
        """Start a new coordination iteration."""
        self.current_iteration += 1
        
        # Capture available answer labels at start of this iteration (freeze snapshot)
        self.iteration_available_labels = []
        for agent_id, answers_list in self.answers_by_agent.items():
            if answers_list:  # Agent has provided at least one answer
                latest_answer = answers_list[-1]  # Get most recent answer
                self.iteration_available_labels.append(latest_answer.label)  # e.g., "agent1.1"
        
        self._add_event("iteration_start", None, f"Starting coordination iteration {self.current_iteration}", 
                       {"iteration": self.current_iteration, "available_answers": self.iteration_available_labels.copy()})

    def change_status(self, agent_id: str, new_status: str):
        """Record when an agent changes status."""
        self._add_event("status_change", agent_id, f"Changed to status: {new_status}")

    def track_agent_context(self, agent_id: str, answers: Dict[str, str], conversation_history: Optional[Dict[str, Any]] = None):
        """Record when an agent receives context."""
        context = {
            "available_answers": list(answers.keys()),
            "answer_count": len(answers),
            "has_conversation_history": bool(conversation_history)
        }
        self._add_event("context_received", agent_id, 
                       f"Received context with {len(answers)} answers", context)

    def track_restart_signal(self, triggering_agent: str, agents_restarted: List[str]):
        """Record when a restart is triggered."""
        # Log restart event with current round first (before incrementing)
        context = {"affected_agents": agents_restarted, "new_round": self.current_round + 1}
        self._add_event("restart_triggered", triggering_agent, 
                       f"Triggered restart affecting {len(agents_restarted)} agents - Starting round {self.current_round + 1}", context)
        
        # Now increment round since we have a new answer triggering restart
        self.current_round += 1
        
        # Mark all restarting agents as RESTARTING status
        for agent_id in agents_restarted:
            if agent_id != triggering_agent:  # Triggering agent already has ANSWERED status
                self.change_status(agent_id, AgentStatus.RESTARTING)

    def add_agent_answer(self, agent_id: str, answer: str):
        """Record when an agent provides a new answer."""
        # Create answer object
        agent_answer = AgentAnswer(
            agent_id=agent_id,
            content=answer,
            timestamp=time.time(),
            is_final=False
        )
        
        # Auto-generate label based on agent position and answer count
        agent_num = self.agent_ids.index(agent_id) + 1
        answer_num = len(self.answers_by_agent[agent_id]) + 1
        label = f"agent{agent_num}.{answer_num}"
        agent_answer.label = label
        
        # Store the answer
        self.answers_by_agent[agent_id].append(agent_answer)
        self.all_answers[label] = answer  # Quick lookup by label
        
        # Record event with label (important info) but no preview (that's for display only)
        context = {"label": label}
        self._add_event("new_answer", agent_id, f"Provided answer {label}", context)

    def add_agent_vote(self, agent_id: str, vote_data: Dict[str, Any]):
        """Record when an agent votes."""
        # Handle both "voted_for" and "agent_id" keys (orchestrator uses "agent_id")
        voted_for = vote_data.get("voted_for") or vote_data.get("agent_id", "unknown")
        reason = vote_data.get("reason", "")
        
        # Convert real agent IDs to anonymous IDs and answer labels
        voter_anon_id = self._get_anonymous_agent_id(agent_id)
        
        # Find the voted-for answer label (agent1.1, agent2.1, etc.)
        voted_for_label = "unknown"
        if voted_for in self.agent_ids:
            # Find the latest answer from the voted-for agent at vote time
            voted_agent_answers = self.answers_by_agent.get(voted_for, [])
            if voted_agent_answers:
                voted_for_label = voted_agent_answers[-1].label
        
        # Store the vote
        vote = AgentVote(
            voter_id=agent_id,
            voted_for=voted_for,
            voted_for_label=voted_for_label,
            voter_anon_id=voter_anon_id,
            reason=reason,
            timestamp=time.time(),
            available_answers=self.iteration_available_labels.copy()
        )
        self.votes.append(vote)
        
        # Record event - only essential info in context
        context = {
            "voted_for": voted_for,  # Real agent ID for compatibility
            "voted_for_label": voted_for_label,  # Answer label for display
            "reason": reason,
            "available_answers": self.iteration_available_labels.copy()
        }
        self._add_event("vote_cast", agent_id, f"Voted for {voted_for_label}", context)

    def set_final_agent(self, agent_id: str, vote_summary: str, all_answers: Dict[str, str]):
        """Record when final agent is selected."""
        self.final_winner = agent_id
        context = {
            "vote_summary": vote_summary,
            "all_answers": list(all_answers.keys()),
            "answers_for_context": all_answers  # Full answers provided to final agent
        }
        self._add_event("final_agent_selected", agent_id, "Selected as final presenter", context)

    def set_final_answer(self, agent_id: str, final_answer: str):
        """Record the final answer presentation."""
        # Create final answer object
        final_answer_obj = AgentAnswer(
            agent_id=agent_id,
            content=final_answer,
            timestamp=time.time(),
            is_final=True
        )
        
        # Auto-generate final label
        agent_num = self.agent_ids.index(agent_id) + 1
        label = f"agent{agent_num}.final"
        final_answer_obj.label = label
        
        # Store the final answer
        self.answers_by_agent[agent_id].append(final_answer_obj)
        self.all_answers[label] = final_answer
        
        # Record event with label only (no preview)
        context = {"label": label}
        self._add_event("final_answer", agent_id, f"Presented final answer {label}", context)
        # Don't end session here - let the orchestrator control when session ends

    def start_final_round(self, selected_agent_id: str):
        """Start the final presentation round."""
        self.is_final_round = True
        # Increment to a special "final" round
        self.current_round += 1
        self.final_winner = selected_agent_id
        
        # Mark winner as starting final presentation
        self.change_status(selected_agent_id, AgentStatus.STREAMING)
        
        self._add_event("final_round_start", selected_agent_id, 
                       f"Starting final presentation round {self.current_round}", 
                       {"round_type": "final"})

    def track_agent_action(self, agent_id: str, action_type, details: str = ""):
        """Track any agent action using ActionType enum."""
        if action_type == ActionType.NEW_ANSWER:
            # For answers, details should be the actual answer content
            self.add_agent_answer(agent_id, details)
        elif action_type == ActionType.VOTE:
            # For votes, details should be vote data dict - but this needs to be handled separately
            # since add_agent_vote expects a dict, not a string
            pass  # Use add_agent_vote directly
        else:
            # For errors, timeouts, cancellations
            action_name = action_type.value.upper()
            self._add_event(f"agent_{action_type.value}", agent_id, f"{action_name}: {details}" if details else action_name)

    def _add_event(self, event_type: str, agent_id: Optional[str], details: str, context: Optional[Dict[str, Any]] = None):
        """Internal method to add an event."""
        # Automatically include current iteration and round in context
        if context is None:
            context = {}
        context = context.copy()  # Don't modify the original
        context["iteration"] = self.current_iteration
        context["round"] = self.current_round
        
        event = CoordinationEvent(
            timestamp=time.time(),
            event_type=event_type,
            agent_id=agent_id,
            details=details,
            context=context
        )
        self.events.append(event)

    def _end_session(self):
        """Mark the end of the coordination session."""
        self.end_time = time.time()
        duration = self.end_time - (self.start_time or self.end_time)
        self._add_event("session_end", None, f"Session completed in {duration:.1f}s")
    
    def get_all_answers(self) -> Dict[str, str]:
        """Get all answers as a label->content dictionary."""
        return self.all_answers.copy()
    
    def get_answers_for_display(self, max_preview_length: int = 150) -> Dict[str, Dict[str, Any]]:
        """Get answers with preview for display purposes."""
        display_answers = {}
        for label, content in self.all_answers.items():
            preview = content[:max_preview_length] + "..." if len(content) > max_preview_length else content
            display_answers[label] = {
                "content": content,
                "preview": preview,
                "is_final": label.endswith(".final")
            }
        return display_answers
    
    def format_answer_preview(self, content: str, max_length: Optional[int] = None) -> str:
        """Format answer content for display with consistent preview length and ellipsis handling.
        
        Args:
            content: The full answer content
            max_length: Override default preview length (uses self.preview_length if None)
            
        Returns:
            Formatted preview string with ellipsis only if actually truncated
        """
        if not content:
            return "No content"
        
        length = max_length if max_length is not None else self.preview_length
        
        # Remove leading/trailing whitespace and normalize line breaks
        cleaned = content.strip().replace('\n', ' ').replace('\r', ' ')
        
        # Replace multiple spaces with single space
        import re
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Only add ellipsis if we're actually truncating
        if len(cleaned) <= length:
            return cleaned
        else:
            return cleaned[:length].rstrip() + "..."
    
    def get_summary(self) -> Dict[str, Any]:
        """Get session summary statistics."""
        duration = (self.end_time or time.time()) - (self.start_time or time.time())
        restart_count = len([e for e in self.events if e.event_type == "restart_triggered"])
        
        return {
            "duration": duration,
            "total_events": len(self.events),
            "total_restarts": restart_count,
            "total_answers": len([label for label in self.all_answers if not label.endswith(".final")]),
            "final_winner": self.final_winner,
            "agent_count": len(self.agent_ids)
        }
    
    def save_coordination_logs(self, log_dir):
        """Save all coordination data and create timeline visualization."""
        try:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Save raw events
            events_file = log_dir / "coordination_events.json"
            with open(events_file, 'w', encoding='utf-8') as f:
                events_data = [event.to_dict() for event in self.events]
                json.dump(events_data, f, indent=2, default=str)
            
            # Save all answers with labels
            answers_file = log_dir / "answers.json"
            with open(answers_file, 'w', encoding='utf-8') as f:
                # Include both the dictionary and the detailed list
                answers_data = {
                    "all_answers": self.all_answers,  # label -> content mapping
                    "by_agent": {
                        agent_id: [
                            {
                                "label": answer.label,
                                "content": answer.content,
                                "timestamp": answer.timestamp,
                                "is_final": answer.is_final
                            } for answer in answers
                        ] for agent_id, answers in self.answers_by_agent.items()
                    }
                }
                json.dump(answers_data, f, indent=2, default=str)
            
            # Save individual answer files
            for label, content in self.all_answers.items():
                answer_file = log_dir / f"answer_{label}.txt"
                with open(answer_file, 'w', encoding='utf-8') as f:
                    f.write(f"ANSWER: {label}\n")
                    f.write("=" * 50 + "\n")
                    agent_id = self._get_agent_id_from_label(label)
                    f.write(f"Agent: {agent_id}\n")
                    f.write(f"Type: {'Final Answer' if label.endswith('.final') else 'Regular Answer'}\n")
                    f.write("-" * 50 + "\n")
                    f.write(content)
            
            # Save votes
            if self.votes:
                votes_file = log_dir / "votes.json"
                with open(votes_file, 'w', encoding='utf-8') as f:
                    votes_data = [
                        {
                            "voter_id": vote.voter_id,
                            "voted_for": vote.voted_for,
                            "voted_for_label": vote.voted_for_label,
                            "voter_anon_id": vote.voter_anon_id,
                            "reason": vote.reason,
                            "timestamp": vote.timestamp,
                            "available_answers": vote.available_answers
                        } for vote in self.votes
                    ]
                    json.dump(votes_data, f, indent=2, default=str)
            
            # Create timeline visualization
            self._create_timeline_file(log_dir)
            
            # Create simplified agent-grouped timeline
            self._create_simplified_timeline_file(log_dir)
            
            # Create round-based timeline
            self._create_round_timeline_file(log_dir)
            
            print(f"💾 Coordination logs saved to: {log_dir}")
            
        except Exception as e:
            print(f"Failed to save coordination logs: {e}")
    
    def _get_agent_id_from_label(self, label: str) -> str:
        """Extract agent_id from a label like 'agent1.1' or 'agent2.final'."""
        # Extract agent number from label
        import re
        match = re.match(r'agent(\d+)', label)
        if match:
            agent_num = int(match.group(1))
            if 0 < agent_num <= len(self.agent_ids):
                return self.agent_ids[agent_num - 1]
        return "unknown"
    
    def _create_timeline_file(self, log_dir):
        """Create the text-based timeline visualization file."""
        timeline_file = log_dir / "coordination_timeline.txt"
        timeline_steps = self._generate_timeline_steps()
        summary = self.get_summary()
        
        with open(timeline_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 120 + "\n")
            f.write("MASSGEN COORDINATION SUMMARY\n")
            f.write("=" * 120 + "\n\n")
            
            # Description
            f.write("DESCRIPTION:\n")
            f.write("This timeline shows the coordination flow between multiple AI agents.\n")
            f.write("• Context: Previous answers supplied to each agent as background\n")
            f.write("• User Query: The original task/question is always included in each agent's prompt\n")
            f.write("• Coordination: Agents build upon each other's work through answer sharing and voting\n\n")
            
            # Agent mapping
            f.write("AGENT MAPPING:\n")
            for i, agent_id in enumerate(self.agent_ids):
                f.write(f"  Agent{i+1} = {agent_id}\n")
            f.write("\n")
            
            # Summary stats
            f.write(f"Duration: {summary['duration']:.1f}s | ")
            f.write(f"Events: {summary['total_events']} | ")
            f.write(f"Restarts: {summary['total_restarts']} | ")
            f.write(f"Winner: {summary['final_winner'] or 'None'}\n\n")
            
            # Timeline table
            self._write_timeline_table(f, timeline_steps)
            
            # Footer
            f.write("\nKEY CONCEPTS:\n")
            f.write("-" * 20 + "\n")
            f.write("• NEW ANSWER: Agent provides original response\n")
            f.write("• RESTART: Other agents discard work, restart with new context\n")
            f.write("• VOTING: Agents choose best answer from available options\n")
            f.write("• FINAL: Winning agent presents synthesized response\n")
            f.write("• ERROR/TIMEOUT: Agent encounters issues\n\n")
            f.write("=" * 120 + "\n")
    
    def _create_simplified_timeline_file(self, log_dir):
        """Create a simplified timeline that groups each agent's actions clearly."""
        simplified_file = log_dir / "coordination_timeline_simplified.txt"
        
        with open(simplified_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 100 + "\n")
            f.write("MASSGEN COORDINATION TIMELINE (SIMPLIFIED)\n")
            f.write("=" * 100 + "\n\n")
            
            # Description
            f.write("DESCRIPTION:\n")
            f.write("This shows what each agent did during coordination, grouped by action type.\n")
            f.write("Events are shown in chronological order with clear agent attribution.\n\n")
            
            # Agent mapping
            f.write("AGENT MAPPING:\n")
            for i, agent_id in enumerate(self.agent_ids):
                f.write(f"  Agent{i+1} = {agent_id}\n")
            f.write("\n")
            
            # Sort events by timestamp
            sorted_events = sorted(self.events, key=lambda e: e.timestamp)
            
            # Process events grouped by iteration
            f.write("COORDINATION ITERATIONS:\n")
            f.write("-" * 50 + "\n")
            
            # Group events by iteration
            events_by_iteration = {}
            for event in sorted_events:
                # Skip session start/end events
                if event.event_type in ["session_start", "session_end"]:
                    continue
                    
                iteration = event.context.get("iteration", 0) if event.context else 0
                if iteration not in events_by_iteration:
                    events_by_iteration[iteration] = []
                events_by_iteration[iteration].append(event)
            
            # Track current status of all agents
            agent_current_status = {aid: "IDLE" for aid in self.agent_ids}
            
            # Display events grouped by iteration
            for iteration in sorted(events_by_iteration.keys()):
                # Get round number from the first event in this iteration
                current_round = 0
                if events_by_iteration[iteration]:
                    first_event = events_by_iteration[iteration][0]
                    current_round = first_event.context.get("round", 0) if first_event.context else 0
                
                if iteration == 0:
                    f.write("INITIALIZATION:\n")
                else:
                    f.write(f"ITERATION {iteration} (Round {current_round}):\n")
                f.write("  " + "-" * 40 + "\n")
                
                events = events_by_iteration[iteration]
                
                # Process events and update agent statuses
                for event in events:
                    agent_display = self._get_agent_display_name(event.agent_id) if event.agent_id else "System"
                    timestamp_str = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S.%f")[:-3]
                    
                    # Update tracked status if this is a status change event
                    if event.event_type == "status_change" and event.agent_id:
                        # Extract new status from event details (handles all AgentStatus values)
                        for status in ["STREAMING", "ANSWERING", "VOTING", "VOTED", "ANSWERED", 
                                      "RESTARTING", "ERROR", "TIMEOUT", "COMPLETED", "IDLE", "WORKING"]:
                            if status.lower() in event.details.lower():
                                agent_current_status[event.agent_id] = status
                                break
                    
                    f.write(f"  [{timestamp_str}] {agent_display}: ")
                    
                    if event.event_type == "iteration_start":
                        f.write(f"--- Starting coordination iteration ---\n")
                    elif event.event_type == "new_answer":
                        label = event.context.get("label", "unknown") if event.context else "unknown"
                        f.write(f"PROVIDED ANSWER ({label})\n")
                    elif event.event_type == "vote_cast":
                        if event.context:
                            voted_for = event.context.get("agent_id", "unknown")
                            reason = event.context.get("reason", "No reason")
                            f.write(f"VOTED FOR {voted_for} - {reason}\n")
                        else:
                            f.write(f"VOTED (details unavailable)\n")
                    elif event.event_type == "restart_triggered":
                        if event.context:
                            affected = event.context.get("affected_agents", [])
                            new_round = event.context.get("new_round", "?")
                            f.write(f"TRIGGERED RESTART - Affected: {len(affected)} agents, Starting Round {new_round}\n")
                        else:
                            f.write(f"TRIGGERED RESTART\n")
                    elif event.event_type == "status_change":
                        f.write(f"{event.details}\n")
                    elif event.event_type == "final_agent_selected":
                        f.write(f"SELECTED AS FINAL PRESENTER\n")
                    elif event.event_type == "final_answer":
                        label = event.context.get("label", "unknown") if event.context else "unknown"
                        f.write(f"PRESENTED FINAL ANSWER ({label})\n")
                    elif event.event_type == "agent_error":
                        f.write(f"ERROR: {event.details}\n")
                    elif event.event_type == "agent_timeout":
                        f.write(f"TIMEOUT: {event.details}\n")
                    elif event.event_type == "agent_cancelled":
                        f.write(f"CANCELLED: {event.details}\n")
                    elif event.event_type == "agent_vote_ignored":
                        f.write(f"VOTE IGNORED: {event.details}\n")
                    elif event.event_type == "agent_restart":
                        f.write(f"RESTARTING: {event.details}\n")
                    else:
                        f.write(f"{event.event_type}: {event.details}\n")
                
                # Show status summary at end of iteration
                f.write("\n  STATUS AT END OF ITERATION:\n")
                for aid in self.agent_ids:
                    agent_display = self._get_agent_display_name(aid)
                    status = agent_current_status.get(aid, "UNKNOWN")
                    f.write(f"    {agent_display}: {status}\n")
                        
                f.write("\n")
            
            f.write("\n")
            
            # Agent-grouped summary
            f.write("AGENT ACTION SUMMARY:\n")
            f.write("=" * 50 + "\n")
            
            for agent_id in self.agent_ids:
                agent_display = self._get_agent_display_name(agent_id)
                f.write(f"\n{agent_display} ({agent_id}):\n")
                f.write("-" * 30 + "\n")
                
                agent_events = [e for e in sorted_events if e.agent_id == agent_id]
                if not agent_events:
                    f.write("  (No recorded actions)\n")
                    continue
                
                for event in agent_events:
                    timestamp_str = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
                    
                    if event.event_type == "new_answer":
                        label = event.context.get("label", "unknown") if event.context else "unknown"
                        f.write(f"  [{timestamp_str}] Provided answer: {label}\n")
                        
                    elif event.event_type == "vote_cast":
                        if event.context:
                            voted_for = event.context.get("voted_for", "unknown")
                            reason = event.context.get("reason", "No reason")
                            f.write(f"  [{timestamp_str}] Voted for: {voted_for} ({reason})\n")
                        
                    elif event.event_type == "restart_triggered":
                        f.write(f"  [{timestamp_str}] Triggered coordination restart\n")
                        
                    elif event.event_type == "status_change":
                        f.write(f"  [{timestamp_str}] Status: {event.details}\n")
                        
                    elif event.event_type == "final_answer":
                        label = event.context.get("label", "unknown") if event.context else "unknown"
                        f.write(f"  [{timestamp_str}] Presented final answer: {label}\n")
            
            f.write("\n" + "=" * 100 + "\n")

    def _create_round_timeline_file(self, log_dir):
        """Create a round-focused timeline that groups events by coordination rounds."""
        round_file = log_dir / "coordination_rounds.txt"
        
        with open(round_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 100 + "\n")
            f.write("MASSGEN COORDINATION ROUNDS\n")
            f.write("=" * 100 + "\n\n")
            
            # Description
            f.write("DESCRIPTION:\n")
            f.write("This shows coordination organized by rounds (stable answer set windows).\n")
            f.write("A new round starts when any agent provides a new answer.\n\n")
            
            # Agent mapping
            f.write("AGENT MAPPING:\n")
            for i, agent_id in enumerate(self.agent_ids):
                f.write(f"  Agent{i+1} = {agent_id}\n")
            f.write("\n")
            
            # Sort events by timestamp
            sorted_events = sorted(self.events, key=lambda e: e.timestamp)
            
            # Group events by round
            events_by_round = {}
            for event in sorted_events:
                if event.event_type in ["session_start", "session_end"]:
                    continue
                round_num = event.context.get("round", 0) if event.context else 0
                if round_num not in events_by_round:
                    events_by_round[round_num] = {
                        "events": [],
                        "iterations": set(),
                        "start_time": None,
                        "end_time": None,
                        "answers": {},
                        "votes": {},
                        "trigger": None
                    }
                
                round_data = events_by_round[round_num]
                round_data["events"].append(event)
                
                # Track iteration numbers in this round
                if event.context:
                    round_data["iterations"].add(event.context.get("iteration", 0))
                
                # Track timing
                if round_data["start_time"] is None:
                    round_data["start_time"] = event.timestamp
                round_data["end_time"] = event.timestamp
                
                # Track answers and votes
                if event.event_type == "new_answer":
                    label = event.context.get("label", "unknown") if event.context else "unknown"
                    round_data["answers"][event.agent_id] = label
                elif event.event_type == "vote_cast":
                    if event.context:
                        # Store the label for display
                        voted_for_label = event.context.get("voted_for_label", event.context.get("voted_for", "unknown"))
                        round_data["votes"][event.agent_id] = voted_for_label
                elif event.event_type == "restart_triggered":
                    # This triggers the next round - capture the transition info
                    if event.context:
                        next_round = event.context.get("new_round", round_num + 1)
                        round_data["trigger"] = f"{self._get_agent_display_name(event.agent_id)} triggered restart → Round {next_round}"
            
            # Display rounds
            for round_num in sorted(events_by_round.keys()):
                round_data = events_by_round[round_num]
                duration = round_data["end_time"] - round_data["start_time"] if round_data["start_time"] else 0
                iteration_range = f"{min(round_data['iterations'])}-{max(round_data['iterations'])}" if round_data["iterations"] else "0"
                
                # Check if this is a final round
                is_final_round = any(e.event_type == "final_round_start" for e in round_data["events"])
                round_type = "FINAL ROUND" if is_final_round else f"ROUND {round_num}"
                
                f.write("=" * 80 + "\n")
                f.write(f"{round_type}\n")
                if is_final_round:
                    f.write(f"Duration: {duration:.2f}s | Iterations: {iteration_range} | Events: {len(round_data['events'])}\n")
                    f.write("Final presentation by selected winner\n")
                else:
                    f.write(f"Duration: {duration:.2f}s | Iterations: {iteration_range} | Events: {len(round_data['events'])}\n")
                f.write("-" * 80 + "\n\n")
                
                # Key events in this round
                f.write("KEY EVENTS:\n")
                for event in round_data["events"]:
                    # Only show important events
                    if event.event_type in ["new_answer", "vote_cast", "restart_triggered", "agent_error", "agent_timeout", "final_round_start"]:
                        agent_display = self._get_agent_display_name(event.agent_id) if event.agent_id else "System"
                        timestamp_str = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
                        
                        if event.event_type == "new_answer":
                            label = event.context.get("label", "unknown") if event.context else "unknown"
                            f.write(f"  [{timestamp_str}] {agent_display}: PROVIDED ANSWER ({label})\n")
                        elif event.event_type == "vote_cast":
                            if event.context:
                                voted_for_label = event.context.get("voted_for_label", event.context.get("voted_for", "unknown"))
                                f.write(f"  [{timestamp_str}] {agent_display}: VOTED FOR {voted_for_label}\n")
                        elif event.event_type == "restart_triggered":
                            if event.context:
                                next_round = event.context.get("new_round", round_num + 1)
                                f.write(f"  [{timestamp_str}] {agent_display}: TRIGGERED RESTART → Round {next_round}\n")
                        elif event.event_type == "agent_error":
                            f.write(f"  [{timestamp_str}] {agent_display}: ERROR\n")
                        elif event.event_type == "agent_timeout":
                            f.write(f"  [{timestamp_str}] {agent_display}: TIMEOUT\n")
                        elif event.event_type == "final_round_start":
                            f.write(f"  [{timestamp_str}] {agent_display}: STARTED FINAL PRESENTATION\n")
                
                f.write("\n")
                
                # Round summary
                f.write("ROUND SUMMARY:\n")
                if is_final_round:
                    f.write(f"  Final presenter: {self._get_agent_display_name(self.final_winner)}\n")
                    
                    # Show the actual final answer that was presented
                    final_label = None
                    final_content = None
                    agent_num = self.agent_ids.index(self.final_winner) + 1
                    final_label = f"agent{agent_num}.final"
                    final_content = self.all_answers.get(final_label)
                    
                    if final_content:
                        preview = self.format_answer_preview(final_content, max_length=200)
                        f.write(f"  Final answer presented:\n")
                        f.write(f"    {final_label}: {preview}\n")
                    
                    # Show context provided to final agent (from set_final_agent)
                    final_agent_event = None
                    for event in sorted_events:
                        if event.event_type == "final_agent_selected" and event.agent_id == self.final_winner:
                            final_agent_event = event
                            break
                    
                    if final_agent_event and final_agent_event.context:
                        answers_for_context = final_agent_event.context.get("answers_for_context", {})
                        if answers_for_context:
                            f.write(f"  Context provided to final agent:\n")
                            for label, answer_content in answers_for_context.items():
                                preview = self.format_answer_preview(answer_content, max_length=150)
                                f.write(f"    {label}: {preview}\n")
                    
                    f.write(f"  Outcome: Final presentation completed\n")
                else:
                    if round_data["answers"]:
                        f.write(f"  Answers provided:\n")
                        for agent_id, label in round_data["answers"].items():
                            # Get answer preview using consistent formatting
                            content = self.all_answers.get(label, "")
                            preview = self.format_answer_preview(content, max_length=100)
                            f.write(f"    {label}: {preview}\n")
                    else:
                        f.write(f"  Answers provided: []\n")
                        
                    if round_data["votes"]:
                        f.write(f"  Votes cast:\n")
                        
                        # Show available answer options (get from first vote in this round)
                        first_vote_in_round = None
                        for vote in self.votes:
                            if vote.voter_id in round_data["votes"]:
                                first_vote_in_round = vote
                                break
                        
                        if first_vote_in_round and first_vote_in_round.available_answers:
                            f.write(f"    Available answers: {first_vote_in_round.available_answers}\n")
                        
                        for voter, voted_for_label in round_data["votes"].items():
                            # Find the vote with full details for the reason
                            vote_details = None
                            for vote in self.votes:
                                if vote.voter_id == voter and vote.voted_for_label == voted_for_label:
                                    vote_details = vote
                                    break
                            
                            voter_display = self._get_agent_display_name(voter)
                            if vote_details:
                                reason = vote_details.reason or "No reason"
                                f.write(f"    {voter_display} → {voted_for_label} ({reason})\n")
                            else:
                                # Fallback without reason
                                f.write(f"    {voter_display} → {voted_for_label} (No reason available)\n")
                    
                    if round_data["trigger"]:
                        f.write(f"  Outcome: {round_data['trigger']}\n")
                    elif round_data["votes"]:
                        f.write(f"  Outcome: All agents voted\n")
                    else:
                        f.write(f"  Outcome: In progress or incomplete\n")
                
                f.write("\n")
            
            f.write("=" * 100 + "\n")

    def _generate_timeline_steps(self) -> List[Dict[str, Any]]:
        """Generate timeline steps from events for visualization."""
        steps = []
        step_num = 0
        
        # Track what each agent can see (context)
        agent_context = {aid: [] for aid in self.agent_ids}
        # Track current status
        agent_status = {aid: "ANSWERING" for aid in self.agent_ids}
        
        # Step 0: Coordination start
        steps.append({
            "step": step_num,
            "event": "COORDINATION START",
            "agents": {
                aid: {
                    "status": "ANSWERING",
                    "context": [],
                    "details": "Starting to work on task"
                } for aid in self.agent_ids
            }
        })
        step_num += 1
        
        # Sort events by timestamp
        sorted_events = sorted(self.events, key=lambda e: e.timestamp)
        
        for event in sorted_events:
            if event.event_type == "new_answer":
                label = event.context.get("label", "unknown")
                
                # Update context for all agents
                for aid in self.agent_ids:
                    if aid != event.agent_id and label not in agent_context[aid]:
                        agent_context[aid].append(label)
                
                steps.append({
                    "step": step_num,
                    "event": f"NEW ANSWER: {label}",
                    "agents": {
                        aid: {
                            "status": f"NEW: {label}" if aid == event.agent_id else agent_status[aid],
                            "context": agent_context[aid].copy(),
                            "details": f"Provided answer {label}" if aid == event.agent_id else "Waiting for coordination to continue..."
                        } for aid in self.agent_ids
                    }
                })
                # Update status
                agent_status[event.agent_id] = "idle"
                step_num += 1
                
            elif event.event_type == "restart_triggered":
                affected = event.context.get("affected_agents", [])
                
                steps.append({
                    "step": step_num, 
                    "event": f"RESTART triggered by {self._get_agent_display_name(event.agent_id)}",
                    "agents": {
                        aid: {
                            "status": "RESTART" if aid in affected else agent_status[aid],
                            "context": agent_context[aid].copy(),
                            "details": "Previous work discarded, restarting with new context" if aid in affected 
                                      else ("Triggered restart" if aid == event.agent_id else agent_status.get(aid, "idle"))
                        } for aid in self.agent_ids
                    }
                })
                # Update status
                for aid in affected:
                    agent_status[aid] = "ANSWERING"
                step_num += 1
                
            elif event.event_type == "vote_cast":
                voted_for = event.context.get("voted_for", "unknown")
                reason = event.context.get("reason", "")
                
                # Check if we need to create a new voting phase step
                if not steps or "VOTING PHASE" not in steps[-1]["event"]:
                    steps.append({
                        "step": step_num,
                        "event": "VOTING PHASE (system-wide)",
                        "agents": {
                            aid: {
                                "status": f"VOTE: {voted_for}" if aid == event.agent_id else "VOTING",
                                "context": agent_context[aid].copy(),
                                "details": f"Selected: {voted_for}" if aid == event.agent_id else "Evaluating available options..."
                            } for aid in self.agent_ids
                        }
                    })
                    step_num += 1
                else:
                    # Update existing voting step
                    steps[-1]["agents"][event.agent_id] = {
                        "status": f"VOTE: {voted_for}",
                        "context": agent_context[event.agent_id].copy(),
                        "details": f"Selected: {voted_for}\nReasoning: {reason[:100]}..."
                    }
                    
            elif event.event_type == "final_answer":
                label = event.context.get("label", "unknown")
                
                steps.append({
                    "step": step_num,
                    "event": f"FINAL ANSWER: {label}",
                    "agents": {
                        aid: {
                            "status": f"FINAL: {label}" if aid == event.agent_id else "TERMINATED",
                            "context": agent_context[aid].copy(),
                            "details": f"Presented final answer" if aid == event.agent_id else ""
                        } for aid in self.agent_ids
                    }
                })
                step_num += 1
        
        return steps
    
    def _get_agent_display_name(self, agent_id: str) -> str:
        """Get display name for agent (Agent1, Agent2, etc.)."""
        if agent_id in self.agent_ids:
            return f"Agent{self.agent_ids.index(agent_id) + 1}"
        return agent_id
    
    def _get_anonymous_agent_id(self, agent_id: str) -> str:
        """Get anonymous agent ID (agent1, agent2, etc.) for an agent."""
        if agent_id in self.agent_ids:
            return f"agent{self.agent_ids.index(agent_id) + 1}"
        return "unknown"
    
    def _write_timeline_table(self, f, steps):
        """Write the timeline table to file."""
        # Calculate column widths
        col_widths = {
            "step": 8,
            "event": 35,
            "agent": 40  # per agent
        }
        
        # Table header
        f.write("+" + "-" * (col_widths["step"] + col_widths["event"] + len(self.agent_ids) * col_widths["agent"] + len(self.agent_ids) + 2) + "+\n")
        
        header = f"| {'Step':^{col_widths['step']}} | {'Event':^{col_widths['event']}} |"
        for i in range(len(self.agent_ids)):
            header += f" {'Agent' + str(i+1):^{col_widths['agent']}} |"
        f.write(header + "\n")
        
        # Separator
        f.write("|" + "-" * (col_widths["step"] + 2) + "+" + "-" * (col_widths["event"] + 2) + "+")
        for _ in self.agent_ids:
            f.write("-" * (col_widths["agent"] + 2) + "+")
        f.write("\n")
        
        # Table rows
        for step in steps:
            # Main status row
            row = f"| {step['step']:^{col_widths['step']}} | {step['event'][:col_widths['event']]:^{col_widths['event']}} |"
            
            for aid in self.agent_ids:
                agent_info = step["agents"].get(aid, {})
                status = agent_info.get("status", "")[:col_widths["agent"]]
                row += f" {status:^{col_widths['agent']}} |"
            f.write(row + "\n")
            
            # Context and details rows
            has_content = False
            for aid in self.agent_ids:
                agent_info = step["agents"].get(aid, {})
                if agent_info.get("context") or agent_info.get("details"):
                    has_content = True
                    break
            
            if has_content:
                # Context row
                row = f"| {' ':^{col_widths['step']}} | {' ':^{col_widths['event']}} |"
                for aid in self.agent_ids:
                    agent_info = step["agents"].get(aid, {})
                    context = agent_info.get("context", [])
                    if context:
                        context_str = f"Context: {context}"[:col_widths["agent"]]
                    else:
                        context_str = ""
                    row += f" {context_str:^{col_widths['agent']}} |"
                f.write(row + "\n")
                
                # Details row
                row = f"| {' ':^{col_widths['step']}} | {' ':^{col_widths['event']}} |"
                for aid in self.agent_ids:
                    agent_info = step["agents"].get(aid, {})
                    details = agent_info.get("details", "")
                    if details:
                        # Take first line of details
                        details_line = details.split('\n')[0][:col_widths["agent"]]
                    else:
                        details_line = ""
                    row += f" {details_line:^{col_widths['agent']}} |"
                f.write(row + "\n")
            
            # Row separator
            f.write("|" + "-" * (col_widths["step"] + 2) + "+" + "-" * (col_widths["event"] + 2) + "+")
            for _ in self.agent_ids:
                f.write("-" * (col_widths["agent"] + 2) + "+")
            f.write("\n")
        
        # Table footer
        f.write("+" + "-" * (col_widths["step"] + col_widths["event"] + len(self.agent_ids) * col_widths["agent"] + len(self.agent_ids) + 2) + "+\n")
    
    def get_rich_timeline_content(self):
        """Get timeline content for Rich terminal display integration."""
        try:
            timeline_steps = self._generate_timeline_steps()
            summary = self.get_summary()
            
            # Convert to display format with previews
            display_answers = self.get_answers_for_display()
            
            # Add preview to timeline steps
            for step in timeline_steps:
                for agent_id in step["agents"]:
                    agent_info = step["agents"][agent_id]
                    # Add preview if this is an answer step
                    if "NEW:" in agent_info.get("status", "") or "FINAL:" in agent_info.get("status", ""):
                        # Extract label from status
                        import re
                        match = re.search(r'(agent\d+\.\d+|agent\d+\.final)', agent_info["status"])
                        if match:
                            label = match.group(1)
                            if label in display_answers:
                                agent_info["preview"] = f"Preview: {display_answers[label]['preview']}"
            
            return {
                'agent_ids': self.agent_ids,
                'summary': summary,
                'timeline_steps': timeline_steps
            }
        except Exception as e:
            print(f"Failed to generate rich timeline content: {e}")
            return None


### OLD ###

# class EventType(Enum):
#     """Types of coordination events."""
#     # Orchestrator events
#     COORDINATION_START = "coordination_start"
#     COORDINATION_END = "coordination_end"
    
#     # Agent lifecycle events
#     AGENT_START = "agent_start"
#     AGENT_RESTART = "agent_restart"
#     AGENT_COMPLETE = "agent_complete"
#     AGENT_IDLE = "agent_idle"
#     AGENT_TIMEOUT = "agent_timeout"
    
#     # Agent action events
#     AGENT_ANSWERING = "agent_answering"
#     AGENT_VOTING = "agent_voting"
#     AGENT_NEW_ANSWER = "agent_new_answer"
#     AGENT_VOTE_CAST = "agent_vote_cast"
    
#     # Context events
#     CONTEXT_SHARED = "context_shared"
#     CONTEXT_RECEIVED = "context_received"
#     CONTEXT_SNAPSHOT = "context_snapshot"
    
#     # System events
#     RESTART_TRIGGERED = "restart_triggered"
#     CONSENSUS_REACHED = "consensus_reached"
#     TIMEOUT_TRIGGERED = "timeout_triggered"

# @dataclass
# class CoordinationEvent:
#     """Represents a single event in the coordination process."""
#     timestamp: float
#     event_type: EventType
#     agent_id: Optional[str] = None
#     details: Optional[str] = None
#     context: Optional[Dict[str, Any]] = None
    
#     def __post_init__(self):
#         """Ensure timestamp is set."""
#         if self.timestamp is None:
#             self.timestamp = time.time()
    
#     def to_dict(self) -> Dict[str, Any]:
#         """Convert event to dictionary for serialization."""
#         return {
#             "timestamp": self.timestamp,
#             "event_type": self.event_type.value,
#             "agent_id": self.agent_id,
#             "details": self.details,
#             "context": self.context
#         }

# @dataclass
# class AgentCoordinationState:
#     """Tracks the coordination state for a single agent."""
#     agent_id: str
#     status: AgentState = AgentState.IDLE
#     events: List[CoordinationEvent] = field(default_factory=list)
    
#     # Coordination stats
#     answer_count: int = 0
#     vote_count: int = 0
#     restart_count: int = 0
    
#     # Current state
#     current_answer: Optional[str] = None
#     current_vote: Optional[Dict[str, str]] = None
#     has_voted: bool = False
#     has_answered: bool = False
    
#     # Answer versioning (agent_id.answer_num format like agent1.1, agent1.2)
#     answers_provided: List[Dict[str, Any]] = field(default_factory=list)
    
#     # Context tracking - what the agent sees when it starts
#     context_version: int = 0
#     context_received_from: List[str] = field(default_factory=list)
#     context_answers: Dict[str, str] = field(default_factory=dict)  # Answers agent can see
#     conversation_context: Optional[Dict[str, Any]] = None  # Full conversation context
    
#     # Timing
#     start_time: Optional[float] = None
#     end_time: Optional[float] = None
#     total_active_time: float = 0.0
    
#     def add_event(self, event: CoordinationEvent):
#         """Add an event to this agent's timeline."""
#         self.events.append(event)
        
#         # Update status based on event type
#         if event.event_type == EventType.AGENT_START:
#             self.status = AgentState.ANSWERING
#             if self.start_time is None:
#                 self.start_time = event.timestamp
#         elif event.event_type == EventType.AGENT_ANSWERING:
#             self.status = AgentState.ANSWERING
#         elif event.event_type == EventType.AGENT_VOTING:
#             self.status = AgentState.VOTING
#         elif event.event_type == EventType.AGENT_NEW_ANSWER:
#             self.status = AgentState.IDLE
#             self.answer_count += 1
#             self.has_answered = True
#             self.current_answer = event.details
#         elif event.event_type == EventType.AGENT_VOTE_CAST:
#             self.status = AgentState.IDLE
#             self.vote_count += 1
#             self.has_voted = True
#             if event.context:
#                 self.current_vote = event.context
#         elif event.event_type == EventType.AGENT_RESTART:
#             self.status = AgentState.RESTARTING
#             self.restart_count += 1
#             self.has_voted = False  # Reset on restart
#         elif event.event_type == EventType.AGENT_IDLE:
#             self.status = AgentState.IDLE
#         elif event.event_type == EventType.AGENT_COMPLETE:
#             self.status = AgentState.COMPLETED
#             self.end_time = event.timestamp
#         elif event.event_type == EventType.AGENT_TIMEOUT:
#             self.status = AgentState.TIMEOUT
#             self.end_time = event.timestamp
    
#     def get_active_time(self) -> float:
#         """Calculate total active time for this agent."""
#         if not self.events:
#             return 0.0
        
#         active_time = 0.0
#         work_start = None
        
#         for event in self.events:
#             if event.event_type in [EventType.AGENT_START, EventType.AGENT_RESTART]:
#                 work_start = event.timestamp
#             elif event.event_type in [EventType.AGENT_IDLE, EventType.AGENT_COMPLETE, 
#                                     EventType.AGENT_TIMEOUT] and work_start:
#                 active_time += event.timestamp - work_start
#                 work_start = None
        
#         # If still working, add time until now
#         if work_start:
#             active_time += time.time() - work_start
        
#         return active_time

# @dataclass
# class CoordinationTracker:
#     """
#     Tracks the complete coordination process for analysis and visualization.
    
#     This is integrated into the Orchestrator to capture all coordination events,
#     agent states, and context sharing information.
#     """
    
#     # Agent states
#     agent_states: Dict[str, AgentCoordinationState] = field(default_factory=dict)
    
#     # Global events timeline
#     global_events: List[CoordinationEvent] = field(default_factory=list)
    
#     # Context tracking
#     context_versions: Dict[str, int] = field(default_factory=dict)
#     context_snapshots: List[Tuple[float, Dict[str, str]]] = field(default_factory=list)
    
#     # Coordination stats
#     start_time: Optional[float] = None
#     end_time: Optional[float] = None
#     total_rounds: int = 0
#     total_restarts: int = 0
    
#     # Consensus tracking
#     final_winner: Optional[str] = None
#     final_votes: Dict[str, str] = field(default_factory=dict)
#     consensus_reached: bool = False
    
#     def initialize_agents(self, agent_ids: List[str]):
#         """Initialize tracking for a set of agents."""
#         self.start_time = time.time()
#         for agent_id in agent_ids:
#             self.agent_states[agent_id] = AgentCoordinationState(agent_id)
#             self.add_event(EventType.AGENT_IDLE, agent_id, "Initialized")
    
#     def add_event(self, event_type: EventType, agent_id: Optional[str] = None, 
#                   details: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
#         """Add a coordination event."""
#         event = CoordinationEvent(
#             timestamp=time.time(),
#             event_type=event_type,
#             agent_id=agent_id,
#             details=details,
#             context=context
#         )
        
#         # Add to global timeline
#         self.global_events.append(event)
        
#         # Add to agent-specific timeline if applicable
#         if agent_id and agent_id in self.agent_states:
#             self.agent_states[agent_id].add_event(event)
        
#         # Handle special event types
#         if event_type == EventType.AGENT_NEW_ANSWER:
#             self._handle_new_answer(agent_id)
#         elif event_type == EventType.RESTART_TRIGGERED:
#             self.total_restarts += 1
#         elif event_type == EventType.CONSENSUS_REACHED:
#             self.consensus_reached = True
#             self.end_time = time.time()
    
#     def _handle_new_answer(self, answering_agent: str):
#         """Handle context sharing when a new answer is provided."""
#         # Increment global context version
#         version = self.context_versions.get("global", 0) + 1
#         self.context_versions["global"] = version
        
#         # Record context snapshot
#         current_answers = {
#             aid: state.current_answer 
#             for aid, state in self.agent_states.items() 
#             if state.current_answer
#         }
#         self.context_snapshots.append((time.time(), current_answers))
        
#         # Mark context as shared
#         self.add_event(EventType.CONTEXT_SHARED, answering_agent, 
#                       f"Context v{version} shared")
        
#         # Mark other agents as receiving new context
#         for aid in self.agent_states.keys():
#             if aid != answering_agent:
#                 self.agent_states[aid].context_version = version
#                 self.agent_states[aid].context_received_from.append(answering_agent)
#                 self.add_event(EventType.CONTEXT_RECEIVED, aid,
#                               f"Received context v{version} from {answering_agent}")
    
#     def track_agent_start(self, agent_id: str, existing_answers: Dict[str, str], 
#                           conversation_context: Optional[Dict[str, Any]] = None):
#         """Track when an agent starts or restarts."""
#         is_restart = self.agent_states[agent_id].restart_count > 0
#         event_type = EventType.AGENT_RESTART if is_restart else EventType.AGENT_START
        
#         # Store full context information
#         self.agent_states[agent_id].context_answers = existing_answers.copy()
#         self.agent_states[agent_id].conversation_context = conversation_context
        
#         # Create context mapping with answer labels (agent1.1, agent2.1, etc.)
#         answer_labels = {}
#         for i, (aid, answer) in enumerate(existing_answers.items(), 1):
#             agent_num = list(self.agent_states.keys()).index(aid) + 1
#             answer_num = len([a for a in self.agent_states[aid].answers_provided]) or 1
#             answer_labels[f"agent{agent_num}.{answer_num}"] = {
#                 "agent_id": aid,
#                 "content": answer,
#                 "preview": answer[:50] + "..." if len(answer) > 50 else answer
#             }
        
#         context_info = {
#             "existing_answers": list(existing_answers.keys()),
#             "context_version": self.context_versions.get("global", 0),
#             "answer_labels": answer_labels,
#             "has_conversation_history": bool(conversation_context and conversation_context.get("conversation_history"))
#         }
        
#         self.add_event(event_type, agent_id, 
#                       f"Started with {len(existing_answers)} answers",
#                       context_info)
    
#     def track_vote(self, agent_id: str, voted_for: str, reason: str):
#         """Track when an agent votes."""
#         # Get the answer being voted for
#         voted_for_agent_state = self.agent_states.get(voted_for)
#         voted_answer = None
#         answer_label = None
        
#         if voted_for_agent_state and voted_for_agent_state.current_answer:
#             voted_answer = voted_for_agent_state.current_answer
#             # Create answer label (agent1.1, agent2.1, etc.)
#             agent_num = list(self.agent_states.keys()).index(voted_for) + 1
#             answer_num = len(voted_for_agent_state.answers_provided)
#             answer_label = f"agent{agent_num}.{answer_num}"
        
#         # Convert available agent IDs to answer labels
#         available_answer_labels = []
#         for context_agent_id in self.agent_states[agent_id].context_answers.keys():
#             context_agent_num = list(self.agent_states.keys()).index(context_agent_id) + 1
#             # Assume latest answer (could be improved to track specific answer versions)
#             available_answer_labels.append(f"agent{context_agent_num}.1")
        
#         vote_context = {
#             "voted_for": voted_for,
#             "reason": reason,
#             "answer_label": answer_label,
#             "voted_answer": voted_answer,
#             "available_answers": available_answer_labels
#         }
        
#         self.add_event(EventType.AGENT_VOTE_CAST, agent_id,
#                       f"Voted for {answer_label or voted_for}: {reason[:30]}...",
#                       vote_context)
#         self.final_votes[agent_id] = voted_for
    
#     def track_new_answer(self, agent_id: str, answer: str):
#         """Track when an agent provides a new answer."""
#         # Create answer version tracking
#         agent_state = self.agent_states[agent_id]
#         answer_num = len(agent_state.answers_provided) + 1
#         agent_num = list(self.agent_states.keys()).index(agent_id) + 1
#         answer_label = f"agent{agent_num}.{answer_num}"
        
#         # Store full answer with metadata
#         answer_record = {
#             "answer_num": answer_num,
#             "content": answer,
#             "timestamp": time.time(),
#             "label": answer_label
#         }
#         agent_state.answers_provided.append(answer_record)
#         agent_state.current_answer = answer
        
#         # Track the event with answer label
#         display_preview = answer[:80] + "..." if len(answer) > 80 else answer
#         self.add_event(EventType.AGENT_NEW_ANSWER, agent_id, 
#                       f"Answer {answer_label}: {display_preview}",
#                       {"answer_label": answer_label, "full_answer": answer})
    
#     def track_restart_signal(self, triggering_agent: str, agents_restarted: List[str]):
#         """Track when a restart is triggered, both who restarted it and who is affected."""
#         self.add_event(EventType.RESTART_TRIGGERED, triggering_agent,
#                        "Triggered global restart", context={"affected_agents": agents_restarted})
#         for agent_id in agents_restarted:
#             self.add_event(EventType.AGENT_RESTART, agent_id,
#                           f"Restarting due to {triggering_agent}'s trigger")

#     def set_final_winner(self, agent_id: str):
#         """Set the final winning agent."""
#         self.final_winner = agent_id
#         self.add_event(EventType.CONSENSUS_REACHED, agent_id,
#                       "Selected as final presenter")
    
#     def track_final_answer(self, agent_id: str, final_answer: str):
#         """Track the final answer presentation (agentX.final)."""
#         agent_num = list(self.agent_states.keys()).index(agent_id) + 1
#         final_label = f"agent{agent_num}.final"
        
#         # Store final answer
#         final_record = {
#             "answer_num": "final",
#             "content": final_answer,
#             "timestamp": time.time(),
#             "label": final_label
#         }
#         self.agent_states[agent_id].answers_provided.append(final_record)
        
#         # Track the event
#         display_preview = final_answer[:80] + "..." if len(final_answer) > 80 else final_answer
#         self.add_event(EventType.AGENT_NEW_ANSWER, agent_id,
#                       f"Final answer {final_label}: {display_preview}",
#                       {"answer_label": final_label, "full_answer": final_answer, "is_final": True})
    
#     def track_agent_error(self, agent_id: str, error_message: str):
#         """Track when an agent encounters an error."""
#         self.add_event(EventType.AGENT_TIMEOUT, agent_id, 
#                       f"Agent error: {error_message[:100]}...",
#                       {"error": error_message, "error_type": "agent_error"})
        
#         # Update agent status
#         if agent_id in self.agent_states:
#             self.agent_states[agent_id].status = AgentState.TIMEOUT
    
#     def track_agent_terminated(self, agent_id: str):
#         """Track when an agent is terminated/killed."""
#         self.add_event(EventType.AGENT_COMPLETE, agent_id, 
#                       "Agent terminated/killed")
        
#         # Update agent status  
#         if agent_id in self.agent_states:
#             self.agent_states[agent_id].status = AgentState.COMPLETED
    
#     def get_summary(self) -> Dict[str, Any]:
#         """Get a comprehensive summary of the coordination process."""
#         duration = (self.end_time or time.time()) - (self.start_time or 0)
        
#         # Calculate per-agent stats
#         agent_stats = {}
#         for aid, state in self.agent_states.items():
#             agent_stats[aid] = {
#                 "status": state.status.value,
#                 "answer_count": state.answer_count,
#                 "vote_count": state.vote_count,
#                 "restart_count": state.restart_count,
#                 "active_time": state.get_active_time(),
#                 "events_count": len(state.events),
#                 "final_vote": state.current_vote,
#                 "has_answer": state.has_answered
#             }
        
#         return {
#             "duration": duration,
#             "start_time": self.start_time,
#             "end_time": self.end_time,
#             "total_events": len(self.global_events),
#             "total_restarts": self.total_restarts,
#             "context_versions": self.context_versions.get("global", 0),
#             "consensus_reached": self.consensus_reached,
#             "final_winner": self.final_winner,
#             "final_votes": self.final_votes,
#             "agent_stats": agent_stats,
#             "context_snapshots_count": len(self.context_snapshots)
#         }
    
#     def get_timeline(self) -> List[Dict[str, Any]]:
#         """Get the complete event timeline."""
#         return [event.to_dict() for event in self.global_events]
    
#     def get_agent_timeline(self, agent_id: str) -> List[Dict[str, Any]]:
#         """Get timeline for a specific agent."""
#         if agent_id not in self.agent_states:
#             return []
#         return [event.to_dict() for event in self.agent_states[agent_id].events]
    
#     def save_coordination_logs(self, log_dir):
#         """Save comprehensive coordination logs and visualizations."""
#         from .logger_config import logger
        
#         try:
#             # Save raw event logs
#             import json
            
#             # Global events log
#             global_events_file = log_dir / "raw_events_global.json"
#             with open(global_events_file, 'w', encoding='utf-8') as ef:
#                 global_events = self.get_timeline()
#                 json.dump(global_events, ef, indent=2, default=str)
            
#             # Per-agent events
#             for agent_id in self.agent_states.keys():
#                 agent_events = self.get_agent_timeline(agent_id)
#                 if agent_events:
#                     agent_events_file = log_dir / f"raw_events_{agent_id}.json"
#                     with open(agent_events_file, 'w', encoding='utf-8') as ef:
#                         json.dump(agent_events, ef, indent=2, default=str)
            
#             # Create Rich-formatted timeline summary
#             self._create_rich_timeline_summary(log_dir)
            
#             # Save individual answer files
#             self._save_answer_files(log_dir)
            
#             logger.info(f"Coordination logs saved to: {log_dir}")
            
#         except Exception as e:
#             logger.warning(f"Failed to save coordination logs: {e}")
    
#     def get_rich_timeline_content(self):
#         """Get the Rich-formatted timeline content for display integration."""
#         try:
#             from rich.table import Table
#             from rich import box
            
#             # Generate timeline from events - purely event-driven
#             timeline_steps = self._generate_timeline_from_events()
#             agent_ids = list(self.agent_states.keys())
#             summary = self.get_summary()
            
#             # Create header info
#             header_info = {
#                 'agent_ids': agent_ids,
#                 'summary': summary,
#                 'timeline_steps': timeline_steps
#             }
            
#             return header_info
            
#         except Exception as e:
#             logger.warning(f"Failed to generate rich timeline content: {e}")
#             return None
    
#     def _create_rich_timeline_summary(self, log_dir):
#         """Create a principled Rich-formatted timeline based on events."""
#         try:
#             from rich.console import Console
#             from rich.table import Table
#             from rich.panel import Panel
#             from rich.columns import Columns
#             from rich import box
#             import io
            
#             # Generate timeline from events - purely event-driven
#             timeline_steps = self._generate_timeline_from_events()
#             agent_ids = list(self.agent_states.keys())
#             summary = self.get_summary()
            
#             # Create console that captures to string (without colors for file)
#             console_output = io.StringIO()
#             file_console = Console(file=console_output, width=120, force_terminal=False, color_system=None)
            
#             # Create file output
#             file_console.print("=" * 120)
#             file_console.print("MASSGEN COORDINATION SUMMARY")
#             file_console.print("=" * 120)
#             file_console.print()
            
#             # Description
#             file_console.print("DESCRIPTION:")
#             file_console.print("This timeline shows the coordination flow between multiple AI agents.")
#             file_console.print("• Context: Previous answers supplied to each agent as background")
#             file_console.print("• User Query: The original task/question is always included in each agent's prompt")
#             file_console.print("• Coordination: Agents build upon each other's work through answer sharing and voting")
#             file_console.print()
            
#             # Agent mapping
#             file_console.print("AGENT MAPPING:")
#             for i, agent_id in enumerate(agent_ids):
#                 file_console.print(f"  Agent{i+1} = {agent_id}")
#             file_console.print()
            
#             header_text = f"Duration: {summary['duration']:.1f}s | Events: {summary['total_events']} | Restarts: {summary['total_restarts']} | Winner: {summary['final_winner'] or 'None'}"
#             file_console.print(header_text)
#             file_console.print()
            
#             # Create table for file (without colors)
#             table = Table(box=box.ASCII, show_header=True)
#             table.add_column("Step", width=6, justify="center")
#             table.add_column("Event", width=30)
            
#             for i, agent_id in enumerate(agent_ids):
#                 table.add_column(f"Agent{i+1}", width=40, justify="left")
            
#             # Add rows from timeline steps
#             for step in timeline_steps:
#                 row = [str(step["step"]), step["event"]]
                
#                 for agent_id in agent_ids:
#                     agent_info = step["agents"].get(agent_id, {"status": "", "context": ""})
#                     # Combine status and context with proper formatting
#                     cell_content = agent_info['status']
#                     if agent_info.get("context"):
#                         cell_content += f"\n{agent_info['context']}"
#                     row.append(cell_content)
                
#                 table.add_row(*row)
#                 # Add spacing between rows
#                 table.add_row(*["", "", *["" for _ in agent_ids]])
            
#             file_console.print(table)
#             file_console.print()
            
#             # Key concepts for file
#             file_console.print("KEY CONCEPTS:")
#             file_console.print("-" * 20)
#             file_console.print("• NEW ANSWER: Agent provides original response")
#             file_console.print("• RESTART: Other agents discard work, restart with new context")
#             file_console.print("• VOTING: Agents choose best answer from available options")
#             file_console.print("• FINAL: Winning agent presents synthesized response") 
#             file_console.print("• ERROR/TIMEOUT: Agent encounters issues")
#             file_console.print()
#             file_console.print("=" * 120)
            
#             # Save file version
#             timeline_file = log_dir / "coordination_timeline.txt" 
#             with open(timeline_file, 'w', encoding='utf-8') as f:
#                 f.write(console_output.getvalue())
            
#             # NOW PRINT the beautiful Rich version to terminal for immediate viewing
#             terminal_console = Console(width=120, force_terminal=True)
            
#             print("\n" + "="*120)
#             print("📊 MASSGEN COORDINATION TIMELINE (Rich Preview)")
#             print("="*120)
            
#             # Beautiful terminal version with colors
#             terminal_console.print()
            
#             # Description panel
#             description_text = """This timeline shows the coordination flow between multiple AI agents.
# • [bold]Context:[/bold] Previous answers supplied to each agent as background
# • [bold]User Query:[/bold] The original task/question is always included in each agent's prompt  
# • [bold]Coordination:[/bold] Agents build upon each other's work through answer sharing and voting"""
#             terminal_console.print(Panel(description_text, title="[bold green]Description[/bold green]", box=box.ROUNDED))
            
#             # Agent mapping panel
#             agent_mapping_text = "\n".join([f"Agent{i+1} = [cyan]{agent_id}[/cyan]" for i, agent_id in enumerate(agent_ids)])
#             terminal_console.print(Panel(agent_mapping_text, title="[bold green]Agent Mapping[/bold green]", box=box.ROUNDED))
            
#             terminal_console.print(Panel(header_text, title="[bold blue]MASSGEN COORDINATION SUMMARY[/bold blue]", box=box.DOUBLE))
#             terminal_console.print()
            
#             # Colorful table for terminal
#             rich_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
#             rich_table.add_column("Step", style="dim", width=6, justify="center")
#             rich_table.add_column("Event", style="bold", width=30)
            
#             for i, agent_id in enumerate(agent_ids):
#                 rich_table.add_column(f"Agent{i+1}", style="cyan", width=40, justify="left")
            
#             # Add colorful rows
#             for step in timeline_steps:
#                 row = [str(step["step"]), step["event"]]
                
#                 for agent_id in agent_ids:
#                     agent_info = step["agents"].get(agent_id, {"status": "", "context": ""})
#                     status = agent_info['status']
                    
#                     # Add colors based on status type
#                     if "NEW:" in status:
#                         status_text = f"[bold green]{status}[/bold green]"
#                     elif "VOTE:" in status:
#                         status_text = f"[bold blue]{status}[/bold blue]"
#                     elif "FINAL:" in status:
#                         status_text = f"[bold purple]{status}[/bold purple]"
#                     elif "RESTART" in status:
#                         status_text = f"[bold yellow]{status}[/bold yellow]"
#                     elif "ANSWERING" in status:
#                         status_text = f"[bold cyan]{status}[/bold cyan]"
#                     elif "VOTING" in status:
#                         status_text = f"[bold blue]{status}[/bold blue]"
#                     elif "SELECTED FOR FINAL PRESENTATION" in status:
#                         status_text = f"[bold purple]{status}[/bold purple]"
#                     elif "TERMINATED" in status:
#                         status_text = f"[bold red]{status}[/bold red]"
#                     else:
#                         status_text = f"[dim]{status}[/dim]"
                    
#                     # Add full context (not truncated)
#                     if agent_info.get("context"):
#                         status_text += f"\n[dim]{agent_info['context']}[/dim]"
                    
#                     row.append(status_text)
                
#                 rich_table.add_row(*row)
#                 # Add some spacing between rows for clarity
#                 rich_table.add_row(*["", "", *["" for _ in agent_ids]])
            
#             terminal_console.print(rich_table)
#             terminal_console.print()
            
#             # Colorful legend
#             terminal_console.print(Panel(
#                 "[bold]KEY CONCEPTS:[/bold]\n"
#                 "• [green]NEW ANSWER[/green]: Agent provides original response\n" 
#                 "• [yellow]RESTART[/yellow]: Other agents discard work, restart with new context\n"
#                 "• [blue]VOTING[/blue]: Agents choose best answer from available options\n"
#                 "• [purple]FINAL[/purple]: Winning agent presents synthesized response\n"
#                 "• [red]ERROR/TIMEOUT[/red]: Agent encounters issues",
#                 title="[bold]Legend[/bold]",
#                 box=box.ROUNDED
#             ))
            
#             print("="*120)
#             print(f"💾 Full timeline saved to: {timeline_file}")
#             print("="*120 + "\n")
                
#         except ImportError:
#             # Fallback without Rich
#             print("⚠️  Rich not available - using simple timeline format")
#             self._create_simple_timeline_summary(log_dir)
#         except Exception as e:
#             from .logger_config import logger
#             logger.warning(f"Failed to create Rich timeline: {e}")
#             self._create_simple_timeline_summary(log_dir)
    
#     def _generate_timeline_from_events(self):
#         """Generate timeline steps purely from coordination events - no hardcoded logic."""
#         timeline_steps = []
#         step_num = 0
#         agent_ids = list(self.agent_states.keys())
        
#         # Track current agent states based on events
#         context_available = {aid: [] for aid in agent_ids}
#         current_status = {aid: "ANSWERING" for aid in agent_ids}  # Track each agent's current status
        
#         # Step 0: Coordination start - all agents start answering
#         timeline_steps.append({
#             "step": step_num,
#             "event": "COORDINATION START", 
#             "agents": {aid: {"status": "ANSWERING", "context": "Context: []\nStarting to work on task"} for aid in agent_ids}
#         })
#         step_num += 1
        
#         # Sort events by timestamp to ensure chronological order
#         sorted_events = sorted(self.global_events, key=lambda e: e.timestamp)
        
#         # Process global events chronologically  
#         for event in sorted_events:
#             event_type = event.event_type
#             agent_id = event.agent_id
            
#             if event_type == EventType.AGENT_NEW_ANSWER:
#                 # New answer event - derive everything from event context
#                 event_context = event.context or {}
#                 answer_label = event_context.get("answer_label", "unknown")
#                 is_final = event_context.get("is_final", False)
#                 full_answer = event_context.get("full_answer", "")
                
#                 if is_final:
#                     # Final answer
#                     preview = full_answer[:150] + "..." if len(full_answer) > 150 else full_answer
#                     timeline_steps.append({
#                         "step": step_num,
#                         "event": f"FINAL ANSWER: {answer_label}",
#                         "agents": {
#                             aid: {
#                                 "status": f"FINAL: {answer_label}" if aid == agent_id else "TERMINATED",
#                                 "context": f"Context: {context_available[aid]}\nPreview: {preview}" if aid == agent_id else ""
#                             } for aid in agent_ids
#                         }
#                     })
                    
#                     # Update status - presenting agent does final, all others terminated
#                     current_status[agent_id] = f"FINAL: {answer_label}"
#                     for aid in agent_ids:
#                         if aid != agent_id:
#                             current_status[aid] = "TERMINATED"
#                 else:
#                     # Regular answer
#                     used_context = context_available[agent_id] if context_available[agent_id] else []
#                     context_display = str(used_context) if used_context else "[]"
#                     preview = full_answer[:150] + "..." if len(full_answer) > 150 else full_answer
                    
#                     timeline_steps.append({
#                         "step": step_num, 
#                         "event": f"NEW ANSWER: {answer_label}",
#                         "agents": {
#                             aid: {
#                                 "status": f"NEW: {answer_label}" if aid == agent_id else current_status[aid],
#                                 "context": f"Context: {context_display}\nPreview: {preview}" if aid == agent_id 
#                                            else f"Context: {str(context_available[aid]) if context_available[aid] else '[]'}\nWaiting for coordination to continue..."
#                             } for aid in agent_ids
#                         }
#                     })
                    
#                     # Update status and context
#                     current_status[agent_id] = f"NEW: {answer_label}"
#                     for aid in agent_ids:
#                         # Agent who answered goes idle, others get new context
#                         if aid == agent_id:
#                             current_status[aid] = "idle"
#                         if answer_label not in context_available[aid]:
#                             context_available[aid].append(answer_label)
                
#                 step_num += 1
            
#             elif event_type == EventType.RESTART_TRIGGERED:
#                 # Restart event - use agent alias instead of real ID
#                 triggering_agent_num = agent_ids.index(agent_id) + 1 if agent_id in agent_ids else 0
#                 affected_agents = event.context.get("affected_agents", []) if event.context else []
#                 timeline_steps.append({
#                     "step": step_num,
#                     "event": f"RESTART triggered by Agent{triggering_agent_num}",
#                     "agents": {
#                         aid: {
#                             "status": "RESTART" if aid in affected_agents else ("idle" if aid == agent_id else current_status[aid]),
#                             "context": f"Context: {context_available[aid]}\nPrevious work discarded, restarting with new context" if aid in affected_agents 
#                                       else f"Context: {context_available[aid]}\nAnswer completed"
#                         } for aid in agent_ids
#                     }
#                 })
                
#                 # Update status - restarted agents go back to ANSWERING, triggering agent goes idle
#                 for aid in affected_agents:
#                     current_status[aid] = "ANSWERING"
#                 current_status[agent_id] = "idle"  # Agent who triggered restart is now idle
                    
#                 step_num += 1
            
#             elif event_type == EventType.AGENT_VOTE_CAST:
#                 # Check if this is part of a voting phase (multiple votes around same time)
#                 vote_context = event.context or {}
#                 voted_for = vote_context.get("answer_label", "unknown")
#                 reason = vote_context.get("reason", "")
                
#                 # Only add voting step if it's the first vote we see (others will be in same step)
#                 existing_vote_step = next((step for step in reversed(timeline_steps) if "VOTING PHASE" in step["event"]), None)
                
#                 if not existing_vote_step:
#                     # Create new voting phase step
#                     voting_agents = {}
#                     for aid in agent_ids:
#                         if aid == agent_id:
#                             voting_agents[aid] = {
#                                 "status": f"VOTE: {voted_for}", 
#                                 "context": f"Selected: {voted_for}\nReasoning: {reason}"
#                             }
#                         else:
#                             voting_agents[aid] = {
#                                 "status": "VOTING", 
#                                 "context": f"Context: {str(context_available[aid]) if context_available[aid] else '[]'}\nEvaluating available options..."
#                             }
                    
#                     timeline_steps.append({
#                         "step": step_num,
#                         "event": "VOTING PHASE (system-wide)",
#                         "agents": voting_agents
#                     })
                    
#                     # Update status for all agents in voting phase
#                     for aid in agent_ids:
#                         if aid == agent_id:
#                             current_status[aid] = f"VOTE: {voted_for}"
#                         else:
#                             current_status[aid] = "VOTING"
                            
#                     step_num += 1
#                 else:
#                     # Update existing voting step and status
#                     existing_vote_step["agents"][agent_id] = {
#                         "status": f"VOTE: {voted_for}",
#                         "context": f"Selected: {voted_for}\nReasoning: {reason}"
#                     }
#                     current_status[agent_id] = f"VOTE: {voted_for}"
        
#         # Add final agent selection step if we have a consensus reached event
#         consensus_events = [e for e in self.global_events if e.event_type == EventType.CONSENSUS_REACHED]
#         if consensus_events and not any("FINAL ANSWER:" in step["event"] for step in timeline_steps):
#             # Get the winning agent
#             winner_event = consensus_events[-1]  # Latest consensus
#             winner_agent_id = winner_event.agent_id
#             winner_agent_num = agent_ids.index(winner_agent_id) + 1 if winner_agent_id in agent_ids else 0
            
#             timeline_steps.append({
#                 "step": step_num,
#                 "event": f"FINAL PRESENTER SELECTED: Agent{winner_agent_num}",
#                 "agents": {
#                     aid: {
#                         "status": f"SELECTED FOR FINAL PRESENTATION" if aid == winner_agent_id else "TERMINATED",
#                         "context": f"Context: {context_available[aid]}\nChosen to present final synthesized answer" if aid == winner_agent_id 
#                                   else f"Context: {context_available[aid]}\nCoordination complete, standing by"
#                     } for aid in agent_ids
#                 }
#             })
            
#             # Update status
#             for aid in agent_ids:
#                 if aid == winner_agent_id:
#                     current_status[aid] = "SELECTED FOR FINAL PRESENTATION"
#                 else:
#                     current_status[aid] = "TERMINATED"
                    
#             step_num += 1
        
#         return timeline_steps
    
#     def _create_simple_timeline_summary(self, log_dir):
#         """Fallback timeline without Rich."""
#         summary_file = log_dir / "coordination_timeline.txt"
        
#         with open(summary_file, 'w', encoding='utf-8') as f:
#             f.write("MASSGEN COORDINATION TIMELINE\n")
#             f.write("=" * 80 + "\n\n")
            
#             summary = self.get_summary() 
#             f.write(f"Duration: {summary['duration']:.1f}s | Events: {summary['total_events']} | Winner: {summary['final_winner']}\n\n")
            
#             timeline_steps = self._generate_timeline_from_events()
            
#             for step in timeline_steps:
#                 f.write(f"Step {step['step']}: {step['event']}\n")
#                 f.write("-" * 50 + "\n")
                
#                 agent_ids = list(self.agent_states.keys())
#                 for i, aid in enumerate(agent_ids):
#                     agent_info = step["agents"].get(aid, {"status": "", "context": ""})
#                     f.write(f"  Agent{i+1}: {agent_info['status']}\n")
#                     if agent_info.get("context"):
#                         f.write(f"            {agent_info['context']}\n")
#                 f.write("\n")
    
#     def _save_answer_files(self, log_dir):
#         """Save individual answer files."""
#         agent_ids = list(self.agent_states.keys())
        
#         for agent_id, state in self.agent_states.items():
#             agent_num = agent_ids.index(agent_id) + 1
#             for answer in state.answers_provided:
#                 if answer["answer_num"] == "final":
#                     label = f"agent{agent_num}.final"
#                 else:
#                     label = f"agent{agent_num}.{answer['answer_num']}"
                
#                 # Save individual answer file
#                 answer_file = log_dir / f"answer_{label}.txt"
#                 try:
#                     with open(answer_file, 'w', encoding='utf-8') as af:
#                         af.write(f"ANSWER: {label}\n")
#                         af.write("=" * 50 + "\n")
#                         af.write(f"Agent: {agent_id}\n")
#                         af.write(f"Timestamp: {answer['timestamp']}\n")
#                         af.write(f"Type: {'Final Answer' if answer['answer_num'] == 'final' else 'Regular Answer'}\n")
#                         af.write("-" * 50 + "\n")
#                         af.write(answer["content"])
#                         af.write("\n")
#                 except Exception as e:
#                     logger.warning(f"Failed to save answer file {label}: {e}")
