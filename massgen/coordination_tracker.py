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
from .logger_config import logger
from enum import Enum


class EventType(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    ITERATION_START = "iteration_start"
    ITERATION_END = "iteration_end"
    STATUS_CHANGE = "status_change"
    CONTEXT_RECEIVED = "context_received"
    RESTART_TRIGGERED = "restart_triggered"
    RESTART_COMPLETED = "restart_completed"
    NEW_ANSWER = "new_answer"
    VOTE_CAST = "vote_cast"
    FINAL_AGENT_SELECTED = "final_agent_selected"
    FINAL_ANSWER = "final_answer"
    FINAL_ROUND_START = "final_round_start"

    AGENT_ERROR = "agent_error"
    AGENT_TIMEOUT = "agent_timeout"
    AGENT_CANCELLED = "agent_cancelled"


ACTION_TO_EVENT = {
    ActionType.ERROR: EventType.AGENT_ERROR,
    ActionType.TIMEOUT: EventType.AGENT_TIMEOUT,
    ActionType.CANCELLED: EventType.AGENT_CANCELLED,
}


@dataclass
class CoordinationEvent:
    """A single coordination event with timestamp."""

    timestamp: float
    event_type: EventType
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
            "context": self.context,
        }


@dataclass
class AgentAnswer:
    """Represents an answer from an agent."""

    agent_id: str
    content: str
    timestamp: float

    @property
    def label(self) -> str:
        """Auto-generate label based on answer properties."""
        # This will be set by the tracker when it knows agent order
        return getattr(self, "_label", "unknown")

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
    available_answers: List[
        str
    ]  # Available answer labels like ["agent1.1", "agent2.1"]


class CoordinationTracker:
    """
    Principled coordination tracking that simply records what happens.

    The orchestrator tells us exactly what occurred and when, without
    us having to infer or manage complex state transitions.
    """

    def __init__(self):
        # Event log - chronological record of everything that happens
        self.events: List[CoordinationEvent] = []

        # Answer tracking
        self.answers_by_agent: Dict[
            str, List[AgentAnswer]
        ] = {}  # agent_id -> list of regular answers
        self.final_answers: Dict[str, AgentAnswer] = {}  # agent_id -> final answer

        # Vote tracking
        self.votes: List[AgentVote] = []

        # Coordination iteration tracking
        self.current_iteration: int = 0
        self.agent_rounds: Dict[
            str, int
        ] = {}  # Per-agent round tracking - increments when restart completed
        self.agent_round_context: Dict[
            str, Dict[int, List[str]]
        ] = {}  # What context each agent had in each round
        self.iteration_available_labels: List[
            str
        ] = []  # Frozen snapshot of available answer labels for current iteration

        # Restart tracking - track pending restarts per agent
        self.pending_agent_restarts: Dict[
            str, bool
        ] = {}  # agent_id -> is restart pending

        # Session info
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.agent_ids: List[str] = []
        self.final_winner: Optional[str] = None
        self.final_context: Optional[
            Dict[str, Any]
        ] = None  # Context provided to final agent
        self.is_final_round: bool = (
            False  # Track if we're in the final presentation round
        )
        self.user_prompt: Optional[str] = None  # Store the initial user prompt

        # Agent mappings - coordination tracker is the single source of truth
        self.agent_context_labels: Dict[
            str, List[str]
        ] = {}  # Track what labels each agent can see

        # Snapshot mapping - tracks filesystem snapshots for answers/votes
        self.snapshot_mappings: Dict[
            str, Dict[str, Any]
        ] = {}  # label/vote_id -> snapshot info

    def _make_snapshot_path(self, kind: str, agent_id: str, timestamp: str) -> str:
        """Generate standardized snapshot paths.

        Args:
            kind: Type of snapshot ('answer', 'vote', 'final_answer', etc.)
            agent_id: The agent ID
            timestamp: The timestamp or 'final' for final answers

        Returns:
            The formatted path string
        """
        if kind == "final_answer" and timestamp == "final":
            return f"final/{agent_id}/answer.txt"
        if kind == "answer":
            return f"{agent_id}/{timestamp}/answer.txt"
        if kind == "vote":
            return f"{agent_id}/{timestamp}/vote.json"
        return f"{agent_id}/{timestamp}/{kind}.txt"

    def initialize_session(
        self, agent_ids: List[str], user_prompt: Optional[str] = None
    ):
        """Initialize a new coordination session."""
        self.start_time = time.time()
        self.agent_ids = agent_ids.copy()
        self.answers_by_agent = {aid: [] for aid in agent_ids}
        self.user_prompt = user_prompt

        # Initialize per-agent round tracking
        self.agent_rounds = {aid: 0 for aid in agent_ids}
        self.agent_round_context = {
            aid: {0: []} for aid in agent_ids
        }  # Each agent starts in round 0 with empty context
        self.pending_agent_restarts = {aid: False for aid in agent_ids}

        # Initialize agent context tracking
        self.agent_context_labels = {aid: [] for aid in agent_ids}

        self._add_event(
            EventType.SESSION_START, None, f"Started with agents: {agent_ids}"
        )

    # Agent ID utility methods
    def get_anonymous_id(self, agent_id: str) -> str:
        """Get anonymous ID (agent1, agent2) for a full agent ID."""
        agent_num = self._get_agent_number(agent_id)
        return f"agent{agent_num}" if agent_num else agent_id

    def _get_agent_number(self, agent_id: str) -> Optional[int]:
        """Get the 1-based number for an agent (1, 2, 3, etc.)."""
        if agent_id in self.agent_ids:
            return self.agent_ids.index(agent_id) + 1
        return None

    def get_agent_context_labels(self, agent_id: str) -> List[str]:
        """Get the answer labels this agent can currently see."""
        return self.agent_context_labels.get(agent_id, []).copy()

    def get_latest_answer_label(self, agent_id: str) -> Optional[str]:
        """Get the latest answer label for an agent."""
        if agent_id in self.answers_by_agent and self.answers_by_agent[agent_id]:
            return self.answers_by_agent[agent_id][-1].label
        return None

    def get_agent_round(self, agent_id: str) -> int:
        """Get the current round for a specific agent."""
        return self.agent_rounds.get(agent_id, 0)

    @property
    def max_round(self) -> int:
        """Get the highest round number across all agents."""
        return max(self.agent_rounds.values()) if self.agent_rounds else 0

    def start_new_iteration(self):
        """Start a new coordination iteration."""
        self.current_iteration += 1

        # Capture available answer labels at start of this iteration (freeze snapshot)
        self.iteration_available_labels = []
        for agent_id, answers_list in self.answers_by_agent.items():
            if answers_list:  # Agent has provided at least one answer
                latest_answer = answers_list[-1]  # Get most recent answer
                self.iteration_available_labels.append(
                    latest_answer.label
                )  # e.g., "agent1.1"

        self._add_event(
            EventType.ITERATION_START,
            None,
            f"Starting coordination iteration {self.current_iteration}",
            {
                "iteration": self.current_iteration,
                "available_answers": self.iteration_available_labels.copy(),
            },
        )

    def end_iteration(self, reason: str, details: Dict[str, Any] = None):
        """Record how an iteration ended."""
        context = {
            "iteration": self.current_iteration,
            "end_reason": reason,
            "available_answers": self.iteration_available_labels.copy(),
        }
        if details:
            context.update(details)

        self._add_event(
            EventType.ITERATION_END,
            None,
            f"Iteration {self.current_iteration} ended: {reason}",
            context,
        )

    def set_user_prompt(self, prompt: str):
        """Set or update the user prompt."""
        self.user_prompt = prompt

    def change_status(self, agent_id: str, new_status: AgentStatus):
        """Record when an agent changes status."""
        self._add_event(
            EventType.STATUS_CHANGE, agent_id, f"Changed to status: {new_status.value}"
        )

    def track_agent_context(
        self,
        agent_id: str,
        answers: Dict[str, str],
        conversation_history: Optional[Dict[str, Any]] = None,
        agent_full_context: Optional[str] = None,
        snapshot_dir: Optional[str] = None,
    ):
        """Record when an agent receives context.

        Args:
            agent_id: The agent receiving context
            answers: Dict of agent_id -> answer content
            conversation_history: Optional conversation history
            agent_full_context: Optional full context string/dict to save
            snapshot_dir: Optional directory path to save context.txt
        """
        # Convert full agent IDs to their corresponding answer labels using canonical mappings
        answer_labels = []
        for answering_agent_id in answers.keys():
            if (
                answering_agent_id in self.answers_by_agent
                and self.answers_by_agent[answering_agent_id]
            ):
                # Get the most recent answer's label
                latest_answer = self.answers_by_agent[answering_agent_id][-1]
                answer_labels.append(latest_answer.label)

        # Update this agent's context labels using canonical mapping
        self.agent_context_labels[agent_id] = answer_labels.copy()

        # Use anonymous agent IDs for the event context
        anon_answering_agents = [self.get_anonymous_id(aid) for aid in answers.keys()]

        context = {
            "available_answers": anon_answering_agents,  # Anonymous IDs for backward compat
            "available_answer_labels": answer_labels.copy(),  # Store actual labels in event
            "answer_count": len(answers),
            "has_conversation_history": bool(conversation_history),
        }
        self._add_event(
            EventType.CONTEXT_RECEIVED,
            agent_id,
            f"Received context with {len(answers)} answers",
            context,
        )

    def track_restart_signal(self, triggering_agent: str, agents_restarted: List[str]):
        """Record when a restart is triggered - but don't increment rounds yet."""
        # Mark affected agents as having pending restarts
        for agent_id in agents_restarted:
            if (
                True
            ):  # agent_id != triggering_agent:  # Triggering agent doesn't restart themselves
                self.pending_agent_restarts[agent_id] = True

        # Log restart event (no round increment yet)
        context = {
            "affected_agents": agents_restarted,
            "triggering_agent": triggering_agent,
        }
        self._add_event(
            EventType.RESTART_TRIGGERED,
            triggering_agent,
            f"Triggered restart affecting {len(agents_restarted)} agents",
            context,
        )

    def complete_agent_restart(self, agent_id: str):
        """Record when an agent has completed its restart and increment their round.

        Args:
            agent_id: The agent that completed restart
        """
        if not self.pending_agent_restarts.get(agent_id, False):
            # This agent wasn't pending a restart, nothing to do
            return

        # Mark restart as completed
        self.pending_agent_restarts[agent_id] = False

        # Increment this agent's round
        self.agent_rounds[agent_id] += 1
        new_round = self.agent_rounds[agent_id]

        # Store the context this agent will work with in their new round
        if agent_id not in self.agent_round_context:
            self.agent_round_context[agent_id] = {}

        # Log restart completion
        context = {
            "agent_round": new_round,
        }
        self._add_event(
            EventType.RESTART_COMPLETED,
            agent_id,
            f"Completed restart - now in round {new_round}",
            context,
        )

    def add_agent_answer(
        self, agent_id: str, answer: str, snapshot_timestamp: Optional[str] = None
    ):
        """Record when an agent provides a new answer.

        Args:
            agent_id: ID of the agent
            answer: The answer content
            snapshot_timestamp: Timestamp of the filesystem snapshot (if any)
        """
        # Create answer object
        agent_answer = AgentAnswer(
            agent_id=agent_id, content=answer, timestamp=time.time()
        )

        # Auto-generate label based on agent position and answer count
        agent_num = self._get_agent_number(agent_id)
        answer_num = len(self.answers_by_agent[agent_id]) + 1
        label = f"agent{agent_num}.{answer_num}"
        agent_answer.label = label

        # Store the answer
        self.answers_by_agent[agent_id].append(agent_answer)

        # Track snapshot mapping if provided
        if snapshot_timestamp:
            self.snapshot_mappings[label] = {
                "type": "answer",
                "label": label,
                "agent_id": agent_id,
                "timestamp": snapshot_timestamp,
                "iteration": self.current_iteration,
                "round": self.get_agent_round(agent_id),
                "path": self._make_snapshot_path("answer", agent_id, snapshot_timestamp),
            }

        # Record event with label (important info) but no preview (that's for display only)
        context = {"label": label}
        self._add_event(
            EventType.NEW_ANSWER, agent_id, f"Provided answer {label}", context
        )

    def add_agent_vote(
        self,
        agent_id: str,
        vote_data: Dict[str, Any],
        snapshot_timestamp: Optional[str] = None,
    ):
        """Record when an agent votes.

        Args:
            agent_id: ID of the voting agent
            vote_data: Dictionary with vote information
            snapshot_timestamp: Timestamp of the filesystem snapshot (if any)
        """
        # Handle both "voted_for" and "agent_id" keys (orchestrator uses "agent_id")
        voted_for = vote_data.get("voted_for") or vote_data.get("agent_id", "unknown")
        reason = vote_data.get("reason", "")

        # Convert real agent IDs to anonymous IDs and answer labels
        voter_anon_id = self.get_anonymous_id(agent_id)

        # Find the voted-for answer label (agent1.1, agent2.1, etc.)
        voted_for_label = "unknown"
        if voted_for not in self.agent_ids:
            logger.warning(f"Vote from {agent_id} for unknown agent {voted_for}")

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
            available_answers=self.iteration_available_labels.copy(),
        )
        self.votes.append(vote)

        # Track snapshot mapping if provided
        if snapshot_timestamp:
            # Create a meaningful vote label similar to answer labels
            agent_num = self._get_agent_number(agent_id) or 0
            vote_num = len([v for v in self.votes if v.voter_id == agent_id])
            vote_label = f"agent{agent_num}.vote{vote_num}"

            self.snapshot_mappings[vote_label] = {
                "type": "vote",
                "label": vote_label,
                "agent_id": agent_id,
                "timestamp": snapshot_timestamp,
                "voted_for": voted_for,
                "voted_for_label": voted_for_label,
                "iteration": self.current_iteration,
                "round": self.get_agent_round(agent_id),
                "path": self._make_snapshot_path("vote", agent_id, snapshot_timestamp),
            }

        # Record event - only essential info in context
        context = {
            "voted_for": voted_for,  # Real agent ID for compatibility
            "voted_for_label": voted_for_label,  # Answer label for display
            "reason": reason,
            "available_answers": self.iteration_available_labels.copy(),
        }
        self._add_event(
            EventType.VOTE_CAST, agent_id, f"Voted for {voted_for_label}", context
        )

    def set_final_agent(
        self, agent_id: str, vote_summary: str, all_answers: Dict[str, str]
    ):
        """Record when final agent is selected."""
        self.final_winner = agent_id

        # Convert agent IDs to their answer labels
        answer_labels = []
        answers_with_labels = {}
        for aid, answer_content in all_answers.items():
            if aid in self.answers_by_agent and self.answers_by_agent[aid]:
                # Get the latest answer label for this agent from regular answers
                if self.answers_by_agent[aid]:
                    latest_answer = self.answers_by_agent[aid][-1]
                    answer_labels.append(latest_answer.label)
                    answers_with_labels[latest_answer.label] = answer_content

        self.final_context = {
            "vote_summary": vote_summary,
            "all_answers": answer_labels,  # Now contains labels like ["agent1.1", "agent2.1"]
            "answers_for_context": answers_with_labels,  # Now keyed by labels
        }
        self._add_event(
            EventType.FINAL_AGENT_SELECTED,
            agent_id,
            "Selected as final presenter",
            self.final_context,
        )

    def set_final_answer(
        self, agent_id: str, final_answer: str, snapshot_timestamp: Optional[str] = None
    ):
        """Record the final answer presentation.

        Args:
            agent_id: ID of the agent
            final_answer: The final answer content
            snapshot_timestamp: Timestamp of the filesystem snapshot (if any)
        """
        # Create final answer object
        final_answer_obj = AgentAnswer(
            agent_id=agent_id,
            content=final_answer,
            timestamp=time.time(),
        )

        # Auto-generate final label
        agent_num = self._get_agent_number(agent_id)
        label = f"agent{agent_num}.final"
        final_answer_obj.label = label

        # Store the final answer separately
        self.final_answers[agent_id] = final_answer_obj

        # Track snapshot mapping if provided
        if snapshot_timestamp:
            self.snapshot_mappings[label] = {
                "type": "final_answer",
                "label": label,
                "agent_id": agent_id,
                "timestamp": snapshot_timestamp,
                "iteration": self.current_iteration,
                "round": self.get_agent_round(agent_id),
                "path": self._make_snapshot_path(
                    "final_answer", agent_id, snapshot_timestamp
                ),
            }

        # Record event with label only (no preview)
        context = {"label": label, **(self.final_context or {})}
        self._add_event(
            EventType.FINAL_ANSWER, agent_id, f"Presented final answer {label}", context
        )

    def start_final_round(self, selected_agent_id: str):
        """Start the final presentation round."""
        self.is_final_round = True
        # Set the final round to be max round across all agents + 1
        final_round = self.max_round + 1
        self.agent_rounds[selected_agent_id] = final_round
        self.final_winner = selected_agent_id

        # Mark winner as starting final presentation
        self.change_status(selected_agent_id, AgentStatus.STREAMING)

        self._add_event(
            EventType.FINAL_ROUND_START,
            selected_agent_id,
            f"Starting final presentation round {final_round}",
            {"round_type": "final", "final_round": final_round},
        )

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
            event_type = ACTION_TO_EVENT.get(action_type)
            if event_type is None:
                raise ValueError(f"Unsupported ActionType: {action_type}")
            message = (
                f"{action_type.value.upper()}: {details}"
                if details
                else action_type.value.upper()
            )
            self._add_event(event_type, agent_id, message)

    def _add_event(
        self,
        event_type: EventType,
        agent_id: Optional[str],
        details: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Internal method to add an event."""
        # Automatically include current iteration and round in context
        if context is None:
            context = {}
        context = context.copy()  # Don't modify the original
        context["iteration"] = self.current_iteration

        # Include agent-specific round if agent_id is provided, otherwise use max round
        if agent_id:
            context["round"] = self.get_agent_round(agent_id)
        else:
            context["round"] = self.max_round

        event = CoordinationEvent(
            timestamp=time.time(),
            event_type=event_type,
            agent_id=agent_id,
            details=details,
            context=context,
        )
        self.events.append(event)

    def _end_session(self):
        """Mark the end of the coordination session."""
        self.end_time = time.time()
        duration = self.end_time - (self.start_time or self.end_time)
        self._add_event(
            EventType.SESSION_END, None, f"Session completed in {duration:.1f}s"
        )

    @property
    def all_answers(self) -> Dict[str, str]:
        """Get all answers as a label->content dictionary."""
        result = {}
        # Add regular answers
        for answers in self.answers_by_agent.values():
            for answer in answers:
                result[answer.label] = answer.content
        # Add final answers
        for answer in self.final_answers.values():
            result[answer.label] = answer.content
        return result

    def get_summary(self) -> Dict[str, Any]:
        """Get session summary statistics."""
        duration = (self.end_time or time.time()) - (self.start_time or time.time())
        restart_count = len(
            [e for e in self.events if e.event_type == EventType.RESTART_TRIGGERED]
        )

        return {
            "duration": duration,
            "total_events": len(self.events),
            "total_restarts": restart_count,
            "total_answers": sum(
                len(answers) for answers in self.answers_by_agent.values()
            ),
            "final_winner": self.final_winner,
            "agent_count": len(self.agent_ids),
        }

    def save_coordination_logs(self, log_dir):
        """Save all coordination data and create timeline visualization.

        Args:
            log_dir: Directory to save logs
            format_style: "old", "new", or "both" (default)
        """
        try:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)

            # Save raw events with session metadata
            events_file = log_dir / "coordination_events.json"
            with open(events_file, "w", encoding="utf-8") as f:
                events_data = [event.to_dict() for event in self.events]

                # Include session metadata at the beginning of the JSON
                session_data = {
                    "session_metadata": {
                        "user_prompt": self.user_prompt,
                        "agent_ids": self.agent_ids,
                        "start_time": self.start_time,
                        "end_time": self.end_time,
                        "final_winner": self.final_winner,
                    },
                    "events": events_data,
                }
                json.dump(session_data, f, indent=2, default=str)

            # Save snapshot mappings to track filesystem snapshots
            if self.snapshot_mappings:
                snapshot_mappings_file = log_dir / "snapshot_mappings.json"
                with open(snapshot_mappings_file, "w", encoding="utf-8") as f:
                    json.dump(self.snapshot_mappings, f, indent=2, default=str)

            # Generate coordination table using the new table generator
            try:
                self._generate_coordination_table(log_dir, session_data)
            except Exception as e:
                logger.warning(
                    f"Warning: Could not generate coordination table: {e}",
                    exc_info=True,
                )

        except Exception as e:
            logger.warning(f"Failed to save coordination logs: {e}", exc_info=True)

    def _generate_coordination_table(self, log_dir, session_data):
        """Generate coordination table using the create_coordination_table.py module."""
        try:
            # Import the table builder
            from massgen.frontend.displays.create_coordination_table import (
                CoordinationTableBuilder,
            )

            # Create the event-driven table directly from session data (includes metadata)
            builder = CoordinationTableBuilder(session_data)
            table_content = builder.generate_event_table()

            # Save the table to a file
            table_file = log_dir / "coordination_table.txt"
            with open(table_file, "w", encoding="utf-8") as f:
                f.write(table_content)

            logger.info(f"Coordination table generated at {table_file}")

        except Exception as e:
            logger.warning(f"Error generating coordination table: {e}", exc_info=True)

    def _get_agent_id_from_label(self, label: str) -> str:
        """Extract agent_id from a label like 'agent1.1' or 'agent2.final'."""
        import re

        match = re.match(r"agent(\d+)", label)
        if match:
            agent_num = int(match.group(1))
            if 0 < agent_num <= len(self.agent_ids):
                return self.agent_ids[agent_num - 1]
        return "unknown"

    def _get_agent_display_name(self, agent_id: str) -> str:
        """Get display name for agent (Agent1, Agent2, etc.)."""
        agent_num = self._get_agent_number(agent_id)
        return f"Agent{agent_num}" if agent_num else agent_id

