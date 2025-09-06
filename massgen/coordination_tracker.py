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
        self.pending_restarts: Set[str] = set()  # Agents that need to restart for current round
        self.final_winner: Optional[str] = None
        self.final_context: Optional[Dict[str, Any]] = None  # Context provided to final agent
        self.is_final_round: bool = False  # Track if we're in the final presentation round
        self.user_prompt: Optional[str] = None  # Store the initial user prompt
        
        # Answer formatting settings
        self.preview_length = 150  # Default preview length for answers

    def initialize_session(self, agent_ids: List[str], user_prompt: Optional[str] = None):
        """Initialize a new coordination session."""
        self.start_time = time.time()
        self.agent_ids = agent_ids.copy()
        self.answers_by_agent = {aid: [] for aid in agent_ids}
        self.user_prompt = user_prompt
        
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

    def set_user_prompt(self, prompt: str):
        """Set or update the user prompt."""
        self.user_prompt = prompt

    def change_status(self, agent_id: str, new_status: AgentStatus):
        """Record when an agent changes status."""
        self._add_event("status_change", agent_id, f"Changed to status: {new_status.value}")

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

        # We don't do the below approach as "done" may only have 1 event and that is the event with NEW_ANSWER that causes the restart. So, if we try to track pending restarts we need some logic to track what else is in done versus not, which causes extra complexity, which is unnecessary bc we know a restart just ends all current work and starts fresh.
        # Track which agents need to restart and ensure that all do indeed restart before incrementing round
        # self.pending_restarts: Set[str] = set(agents_restarted)  #  - {triggering_agent}  # bc the triggering agent won't restart
        
        # Below should be done already.
        # # Mark all restarting agents as RESTARTING status
        # for agent_id in agents_restarted:
        #     if agent_id != triggering_agent:  # Triggering agent already has ANSWERED status
        #         self.change_status(agent_id, AgentStatus.RESTARTING)

    # def agent_restarted(self, agent_id: str):
    #     """Record when an agent has completed its restart. If all have restarted, increment round."""
    #     self.change_status(agent_id, AgentStatus.RESTARTING)
    #     self.pending_restarts.remove(agent_id)
    #     if not self.pending_restarts:
    #         # All agents have restarted - increment round
    #         self.current_round += 1
    #         self._add_event("restart_complete", None, f"All agents restarted - Now in round {self.current_round}")

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
        self.final_context = {
            "vote_summary": vote_summary,
            "all_answers": list(all_answers.keys()),
            "answers_for_context": all_answers  # Full answers provided to final agent
        }
        self._add_event("final_agent_selected", agent_id, "Selected as final presenter", self.final_context)

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
        context = {"label": label, **(self.final_context or {})}
        self._add_event("final_answer", agent_id, f"Presented final answer {label}", context)

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
        
        # Only add ellipsis if we're actually truncating
        if len(content) <= length:
            return content
        else:
            return content[:length].rstrip() + "..."
    
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
    
    def save_coordination_logs(self, log_dir, format_style="both"):
        """Save all coordination data and create timeline visualization.
        
        Args:
            log_dir: Directory to save logs
            format_style: "old", "new", or "both" (default)
        """
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
            
            # Create round-based timeline based on format preference
            if format_style in ["old", "both"]:
                self._create_round_timeline_file_old(log_dir)
            if format_style in ["new", "both"]:
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
            f.write("• NEW ANSWER: Agent provides a new response given the initial user query and the supplied context\n")
            f.write("• RESTART: Agent restarts with new context\n")
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
                        # Extract new status from event details using enum values
                        enum_statuses = [status.value.upper() for status in AgentStatus]
                        custom_statuses = ["IDLE", "WORKING"]  # Non-enum statuses
                        all_statuses = enum_statuses + custom_statuses
                        
                        for status in all_statuses:
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
        """Create a round-focused timeline with table display (new format)."""
        round_file = log_dir / "coordination_rounds.txt"
        
        with open(round_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 120 + "\n")
            f.write("MASSGEN COORDINATION ROUNDS - TABLE VIEW\n")
            f.write("=" * 120 + "\n\n")
            
            # Description
            f.write("DESCRIPTION:\n")
            f.write("This shows coordination organized by rounds in a table format similar to coordination_timeline.txt.\n")
            f.write("A new round starts when any agent provides a new answer.\n\n")
            
            # Agent mapping
            f.write("AGENT MAPPING:\n")
            for i, agent_id in enumerate(self.agent_ids):
                f.write(f"  Agent{i+1} = {agent_id}\n")
            f.write("\n")
            
            # Summary stats
            summary = self.get_summary()
            f.write(f"Duration: {summary['duration']:.1f}s | ")
            f.write(f"Rounds: {self.current_round + 1} | ")
            f.write(f"Winner: {summary['final_winner'] or 'None'}\n\n")
            
            # Generate rounds for table display
            rounds_data = self._generate_rounds_for_table()
            
            # Write the table (with initial user prompt)
            self._write_rounds_table(f, rounds_data)
            
            f.write("\nKEY CONCEPTS:\n")
            f.write("-" * 20 + "\n")
            f.write("• NEW ANSWER: Agent provides original response\n")
            f.write("• RESTART: Other agents discard work, restart with new context\n")
            f.write("• VOTING: Agents choose best answer from available options\n")
            f.write("• FINAL: Winning agent presents synthesized response\n")
            f.write("• ERROR/TIMEOUT: Agent encounters issues\n\n")
            f.write("=" * 120 + "\n")
    
    def _generate_rounds_for_table(self) -> List[Dict[str, Any]]:
        """Generate round steps from events for table visualization."""
        rounds = []
        
        # Sort events by timestamp
        sorted_events = sorted(self.events, key=lambda e: e.timestamp)
        
        # Group events by round
        events_by_round = {}
        for event in sorted_events:
            if event.event_type in ["session_start", "session_end"]:
                continue
            round_num = event.context.get("round", 0) if event.context else 0
            if round_num not in events_by_round:
                events_by_round[round_num] = []
            events_by_round[round_num].append(event)
        
        # Build context map from actual context_received events
        agent_context_by_iteration = {aid: {} for aid in self.agent_ids}
        for event in sorted_events:
            if event.event_type == "context_received" and event.agent_id and event.context:
                iteration = event.context.get("iteration", 0)
                available_answers = event.context.get("available_answers", [])
                # Convert agent IDs to answer labels
                answer_labels = []
                for answer_ref in available_answers:
                    if answer_ref in self.agent_ids:
                        # Find latest answer label for this agent
                        agent_num = self.agent_ids.index(answer_ref) + 1
                        # Find the most recent non-final answer for this agent
                        for label in sorted(self.all_answers.keys()):
                            if label.startswith(f"agent{agent_num}.") and not label.endswith(".final"):
                                answer_labels.append(label)
                                break
                    else:
                        # Already a label
                        answer_labels.append(answer_ref)
                agent_context_by_iteration[event.agent_id][iteration] = answer_labels
        
        # Process each round
        for round_num in sorted(events_by_round.keys()):
            events = events_by_round[round_num]
            
            # Get context for agents in this round from actual context_received events
            round_agent_context = {}
            for aid in self.agent_ids:
                # Find the most recent context for this agent up to this round
                agent_context = []
                for iteration in sorted(agent_context_by_iteration[aid].keys()):
                    # Get context from events in this round or earlier rounds
                    round_for_iteration = None
                    for event in sorted_events:
                        if event.context and event.context.get("iteration") == iteration:
                            round_for_iteration = event.context.get("round", 0)
                            break
                    if round_for_iteration is not None and round_for_iteration <= round_num:
                        agent_context = agent_context_by_iteration[aid][iteration]
                round_agent_context[aid] = agent_context
            
            # Initialize round data
            round_data = {
                "round": round_num,
                "events": events,  # Store the events for this round
                "agents": {aid: {"status": AgentStatus.ANSWERING.value.upper(), "context": round_agent_context.get(aid, []), "details": ""} for aid in self.agent_ids},
                "is_final": False
            }
            
            # Process events in this round
            main_event = None
            main_event_type = ""
            
            # First pass: Find the main event that defines this round
            new_answer_event = None
            vote_events = []
            restart_event = None
            final_events = []
            
            for event in events:
                if event.event_type == "new_answer":
                    new_answer_event = event
                elif event.event_type == "vote_cast":
                    vote_events.append(event)
                elif event.event_type == "restart_triggered":
                    restart_event = event
                elif event.event_type in ["final_round_start", "final_answer"]:
                    final_events.append(event)
            
            # Determine the main event for this round
            if new_answer_event:
                # This round shows the new answer
                label = new_answer_event.context.get("label", "unknown") if new_answer_event.context else "unknown"
                main_event_type = f"NEW ANSWER: {label}"
                main_event = new_answer_event
                
                # Update answering agent
                round_data["agents"][new_answer_event.agent_id] = {
                    "status": f"NEW ANSWER: {label}",
                    "context": round_agent_context.get(new_answer_event.agent_id, []),
                    "details": f"Provided answer {label}"
                }
                
                # Update details for other agents
                for aid in self.agent_ids:
                    if aid != new_answer_event.agent_id:
                        round_data["agents"][aid]["details"] = "Waiting for coordination to continue..."
                
                # IMPORTANT: Check if this answer also triggered a restart in the same round
                # if restart_event and restart_event.agent_id == new_answer_event.agent_id:
                #     # This agent provided an answer AND triggered a restart
                #     affected_raw = restart_event.context.get("affected_agents", []) if restart_event.context else []
                    
                #     # Handle both list and string representations of affected_agents
                #     if isinstance(affected_raw, str) and "dict_keys" in affected_raw:
                #         import re
                #         matches = re.findall(r"'([^']+)'", affected_raw)
                #         affected = matches
                #     elif isinstance(affected_raw, list):
                #         affected = affected_raw
                #     else:
                #         affected = []
                    
                #     # Update answering agent to show they triggered restart
                #     round_data["agents"][new_answer_event.agent_id]["details"] = f"Provided {label} → triggered restart"
                    
                #     # Update other affected agents to show restart
                #     for aid in affected:
                #         if aid != new_answer_event.agent_id:
                #             round_data["agents"][aid] = {
                #                 "status": AgentStatus.RESTARTING.value.upper(),
                #                 "context": global_agent_context[aid].copy(),
                #                 "details": "Previous work discarded, restarting with new context"
                #             }
            
            elif vote_events:
                # This is a voting round
                main_event_type = "VOTING PHASE (system-wide)"
                main_event = vote_events[0]
                
                # Update all voting agents
                for vote_event in vote_events:
                    if vote_event.context:
                        voted_for_label = vote_event.context.get("voted_for_label", vote_event.context.get("voted_for", "unknown"))
                        round_data["agents"][vote_event.agent_id] = {
                            "status": f"VOTE: {voted_for_label}",
                            "context": round_agent_context.get(vote_event.agent_id, []),
                            "details": f"Selected: {voted_for_label}"
                        }
            
            elif final_events:
                # This is the final round
                final_answer_event = None
                for event in final_events:
                    if event.event_type == "final_answer":
                        final_answer_event = event
                        break
                
                if final_answer_event:
                    label = final_answer_event.context.get("label", "unknown") if final_answer_event.context else "unknown"
                    main_event_type = f"FINAL ANSWER: {label}"
                    main_event = final_answer_event
                    
                    # Update final agent
                    round_data["agents"][final_answer_event.agent_id] = {
                        "status": f"FINAL ANSWER: {label}",
                        "context": round_agent_context.get(final_answer_event.agent_id, []),
                        "details": "Presented final answer"
                    }
                    
                    # Mark other agents as terminated
                    for aid in self.agent_ids:
                        if aid != final_answer_event.agent_id:
                            round_data["agents"][aid]["status"] = "TERMINATED"
                else:
                    main_event_type = "FINAL ROUND START"
                    main_event = final_events[0]
                    round_data["is_final"] = True
            
            elif restart_event:
                # Show restart as a separate event
                affected_raw = restart_event.context.get("affected_agents", []) if restart_event.context else []
                
                # Handle both list and string representations of affected_agents
                if isinstance(affected_raw, str) and "dict_keys" in affected_raw:
                    # Parse string like "dict_keys(['gpt5nano_1', 'gpt5nano_2'])"
                    import re
                    matches = re.findall(r"'([^']+)'", affected_raw)
                    affected = matches
                elif isinstance(affected_raw, list):
                    affected = affected_raw
                else:
                    affected = []
                
                triggering_agent = self._get_agent_display_name(restart_event.agent_id)
                main_event_type = f"RESTART triggered by {triggering_agent}"
                main_event = restart_event
                
                # Update triggering agent (keeps their answer status)
                round_data["agents"][restart_event.agent_id]["details"] = f"Triggered restart"
                
                # Update all affected agents (not including the triggering agent)
                for aid in affected:
                    if aid != restart_event.agent_id:  # Don't override triggering agent
                        round_data["agents"][aid] = {
                            "status": AgentStatus.RESTARTING.value.upper(),
                            "context": round_agent_context.get(aid, []),
                            "details": "Previous work discarded, restarting with new context"
                        }
            
            # Add the round
            round_data["event"] = main_event_type
            rounds.append(round_data)
        
        return rounds
    
    def _write_rounds_table(self, f, rounds_data):
        """Write the rounds table to file."""
        if not rounds_data:
            return
        
        # Calculate column widths (no events column, wider agent columns)
        col_widths = {
            "round": 8,
            "agent": 60  # wider columns for more detailed info
        }
        
        # Table header
        total_width = col_widths["round"] + len(self.agent_ids) * col_widths["agent"] + len(self.agent_ids) + 2
        f.write("+" + "-" * (total_width - 1) + "+\n")
        
        header = f"| {'Round':^{col_widths['round']}} |"
        for i in range(len(self.agent_ids)):
            header += f" {'Agent' + str(i+1):^{col_widths['agent']}} |"
        f.write(header + "\n")
        
        # Separator
        f.write("|" + "-" * (col_widths["round"] + 2) + "+")
        for _ in self.agent_ids:
            f.write("-" * (col_widths["agent"] + 2) + "+")
        f.write("\n")
        
        # Initial user prompt row (spans all columns)
        if self.user_prompt:
            prompt_preview = self.format_answer_preview(self.user_prompt, max_length=200)
            total_content_width = len(self.agent_ids) * (col_widths["agent"] + 3) - 1  # Account for separators
            
            f.write(f"| {'USER':^{col_widths['round']}} | {prompt_preview:^{total_content_width}} |\n")
            
            # Separator after user prompt
            f.write("|" + "=" * (col_widths["round"] + 2) + "+")
            for _ in self.agent_ids:
                f.write("=" * (col_widths["agent"] + 2) + "+")
            f.write("\n")
        
        # Table rows
        for round_data in rounds_data:
            round_label = f"R{round_data['round']}" if not round_data["is_final"] else "FINAL"
            
            # Create comprehensive cell content for each agent
            agent_cells = []
            for aid in self.agent_ids:
                agent_info = round_data["agents"].get(aid, {})
                cell_lines = []
                
                # Main status line (no "Status:" label, just the status)
                status = agent_info.get("status", "IDLE")
                
                # Format status: keep special statuses as-is, but make basic statuses lowercase with parentheses
                basic_statuses = [
                    AgentStatus.ANSWERING.value.upper(),
                    AgentStatus.VOTING.value.upper(), 
                    AgentStatus.RESTARTING.value.upper(),
                    AgentStatus.ERROR.value.upper(),
                    AgentStatus.TIMEOUT.value.upper(),
                    AgentStatus.COMPLETED.value.upper(),
                    "IDLE", "TERMINATED"  # Custom statuses not in enum
                ]
                if status in basic_statuses:
                    formatted_status = f"({status.lower()})"
                else:
                    # Keep special statuses like "NEW ANSWER: agent1.1" as-is
                    formatted_status = status
                
                cell_lines.append(formatted_status)
                
                # Context-specific information based on status
                if "NEW ANSWER:" in status:
                    # Agent is providing an answer
                    context = agent_info.get("context", [])
                    if context:
                        context_str = ", ".join(context)
                        context_str = self.format_answer_preview(context_str, max_length=45)
                        cell_lines.append(f"Context: [{context_str}]")
                    else:
                        cell_lines.append("Context: []")
                    
                    # Add answer preview
                    import re
                    match = re.search(r'(agent\d+\.\d+|agent\d+\.final)', status)
                    if match:
                        label = match.group(1)
                        answer_content = self.all_answers.get(label, "")
                        if answer_content:
                            preview = self.format_answer_preview(answer_content, max_length=45)
                            cell_lines.append(f"Preview: {preview}")
                
                elif "VOTE:" in status:
                    # Agent is voting
                    # Find vote options from the voting event
                    vote_options = []
                    vote_reason = ""
                    for vote in self.votes:
                        if vote.voter_id == aid and vote.available_answers:
                            vote_options = vote.available_answers
                            vote_reason = vote.reason or ""
                            break
                    
                    if vote_options:
                        options_str = ", ".join(vote_options)
                        options_str = self.format_answer_preview(options_str, max_length=45)
                        cell_lines.append(f"Options: [{options_str}]")
                    
                    if vote_reason:
                        vote_reason = self.format_answer_preview(vote_reason, max_length=45)
                        cell_lines.append(f"Reason: {vote_reason}")
                
                elif "FINAL ANSWER:" in status:
                    # Agent is presenting final answer - use complete context from final_context if available
                    if self.final_context and "answers_for_context" in self.final_context:
                        # Use the complete context provided to the final agent
                        context_answers = list(self.final_context["answers_for_context"].keys())
                        context_str = ", ".join(context_answers)
                        context_str = self.format_answer_preview(context_str, max_length=45)
                        cell_lines.append(f"Context: [{context_str}]")
                    else:
                        # Fallback to agent_info context
                        context = agent_info.get("context", [])
                        if context:
                            context_str = ", ".join(context)
                            context_str = self.format_answer_preview(context_str, max_length=45)
                            cell_lines.append(f"Context: [{context_str}]")
                    
                    # Add final answer preview
                    import re
                    match = re.search(r'(agent\d+\.\d+|agent\d+\.final)', status)
                    if match:
                        label = match.group(1)
                        answer_content = self.all_answers.get(label, "")
                        if answer_content:
                            preview = self.format_answer_preview(answer_content, max_length=45)
                            cell_lines.append(f"Preview: {preview}")
                
                elif status == AgentStatus.RESTARTING.value.upper() or formatted_status == f"({AgentStatus.RESTARTING.value})":
                    # Agent is restarting
                    context = agent_info.get("context", [])
                    if context:
                        context_str = ", ".join(context)
                        context_str = self.format_answer_preview(context_str, max_length=45)
                        cell_lines.append(f"Context: [{context_str}]")
                    cell_lines.append("Restarting with new context")
                
                elif status == "TERMINATED":
                    # Agent is done (but status is already formatted as "(terminated)")
                    pass
                
                else:
                    # Default case (ANSWERING, IDLE, etc.)
                    context = agent_info.get("context", [])
                    if context:
                        context_str = ", ".join(context)
                        context_str = self.format_answer_preview(context_str, max_length=45)
                        cell_lines.append(f"Context: [{context_str}]")
                    else:
                        cell_lines.append("Context: []")
                
                agent_cells.append(cell_lines)
            
            # Calculate number of rows needed
            max_lines = max(len(cell) for cell in agent_cells) if agent_cells else 1
            
            # Check if this round contains actual restart events
            restart_affected_agents = set()
            
            # Look for restart_triggered events in this round's events
            for event in round_data.get("events", []):
                if event.event_type == "restart_triggered":
                    # Found a restart event - extract affected agents
                    if event.context:
                        affected_raw = event.context.get("affected_agents", [])
                        
                        # Handle both list and string representations of affected_agents
                        if isinstance(affected_raw, str) and "dict_keys" in affected_raw:
                            # Parse string like "dict_keys(['gpt5nano_1', 'gpt5nano_2'])"
                            import re
                            matches = re.findall(r"'([^']+)'", affected_raw)
                            affected = matches
                        elif isinstance(affected_raw, list):
                            affected = affected_raw
                        else:
                            affected = []
                        
                        # Add affected agents to the restart set
                        for aid in affected:
                            if aid in self.agent_ids:
                                restart_affected_agents.add(aid)
                    break  # Only need to find one restart event per round
            
            # Write multi-row cell content
            for line_num in range(max_lines):
                if line_num == 0:
                    # First line includes round label
                    row = f"| {round_label:^{col_widths['round']}} |"
                else:
                    # Subsequent lines have empty round column
                    row = f"| {' ':^{col_widths['round']}} |"
                
                for i, (aid, cell_lines) in enumerate(zip(self.agent_ids, agent_cells)):
                    if line_num < len(cell_lines):
                        content = cell_lines[line_num][:col_widths["agent"]]
                        # Center the content
                        row += f" {content:^{col_widths['agent']}} |"
                    elif line_num == 0 and aid in restart_affected_agents and len(restart_affected_agents) > 1:
                        # Show restart indicator across affected agents
                        restart_indicator = "↻ RESTART ↻"
                        row += f" {restart_indicator:^{col_widths['agent']}} |"
                    else:
                        row += f" {' ':^{col_widths['agent']}} |"
                
                f.write(row + "\n")
            
            # Check if this was a restart round and add special separator
            if len(restart_affected_agents) > 0:
                # Special restart separator with visual indicators
                f.write("|" + "~" * (col_widths["round"] + 2) + "+")
                for aid in self.agent_ids:
                    if aid in restart_affected_agents:
                        # Use wave pattern for restarted agents
                        f.write("~" * (col_widths["agent"] + 2) + "+")
                    else:
                        # Normal separator for non-affected agents
                        f.write("-" * (col_widths["agent"] + 2) + "+")
                f.write("\n")
            else:
                # Normal row separator
                f.write("|" + "-" * (col_widths["round"] + 2) + "+")
                for _ in self.agent_ids:
                    f.write("-" * (col_widths["agent"] + 2) + "+")
                f.write("\n")
        
        # Table footer
        f.write("+" + "-" * (total_width - 1) + "+")

    def _create_round_timeline_file_old(self, log_dir):
        """Create a round-focused timeline with text-based display (original format)."""
        round_file = log_dir / "coordination_rounds_old.txt"
        
        with open(round_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 120 + "\n")
            f.write("MASSGEN COORDINATION ROUNDS\n")
            f.write("=" * 120 + "\n\n")
            
            # Description
            f.write("DESCRIPTION:\n")
            f.write("This shows coordination organized by rounds (stable answer set windows).\n")
            f.write("A new round starts when any agent provides a new answer.\n\n")
            
            # Agent mapping
            f.write("AGENT MAPPING:\n")
            for i, agent_id in enumerate(self.agent_ids):
                f.write(f"  Agent{i+1} = {agent_id}\n")
            f.write("\n")
            
            # Summary stats
            summary = self.get_summary()
            f.write(f"Duration: {summary['duration']:.1f}s | ")
            f.write(f"Rounds: {self.current_round + 1} | ")
            f.write(f"Winner: {summary['final_winner'] or 'None'}\n\n")
            
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
                    
                    # Show context provided to final agent (from self.final_context)
                    if self.final_context and "answers_for_context" in self.final_context:
                        f.write(f"  Context provided to final agent:\n")
                        for label, answer_content in self.final_context["answers_for_context"].items():
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
