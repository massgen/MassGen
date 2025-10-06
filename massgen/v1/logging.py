# -*- coding: utf-8 -*-
"""
MassGen Logging System

This module provides comprehensive logging capabilities for the MassGen system,
recording all agent state changes, orchestration events, and system activities
to local files for detailed analysis.
"""

import json
import logging
import os
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import AnswerRecord, LogEntry, VoteRecord


class MassLogManager:
    """
    Comprehensive logging system for the MassGen framework.

    Records all significant events including:
    - Agent state changes (working, voted, failed)
    - Answer updates and notifications
    - Voting events and consensus decisions
    - Phase transitions (collaboration, debate, consensus)
    - System metrics and performance data

    New organized structure:
    logs/
    └── YYYYMMDD_HHMMSS/
        ├── display/
        │   ├── agent_0.txt, agent_1.txt, ...  # Real-time display logs
        │   └── system.txt                     # System messages
        ├── answers/
        │   ├── agent_0.txt, agent_1.txt, ...  # Agent answer histories
        ├── votes/
        │   ├── agent_0.txt, agent_1.txt, ...  # Agent voting records
        ├── events.jsonl                       # Structured event log
        └── console.log                        # Python logging output
    """

    def __init__(
        self,
        log_dir: str = "logs",
        session_id: Optional[str] = None,
        non_blocking: bool = False,
    ):
        """
        Initialize the logging system.

        Args:
            log_dir: Directory to save log files
            session_id: Unique identifier for this session
            non_blocking: If True, disable file logging to prevent hanging issues
        """
        self.base_log_dir = Path(log_dir)
        self.session_id = session_id or self._generate_session_id()
        self.non_blocking = non_blocking

        if self.non_blocking:
            print("⚠️  LOGGING: Non-blocking mode enabled - file logging disabled")

        # Create main session directory
        self.session_dir = self.base_log_dir / self.session_id
        if not self.non_blocking:
            try:
                self.session_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Warning: Failed to create session directory, enabling non-blocking mode: {e}")
                self.non_blocking = True

        # Create subdirectories
        self.display_dir = self.session_dir / "display"
        self.answers_dir = self.session_dir / "answers"
        self.votes_dir = self.session_dir / "votes"

        if not self.non_blocking:
            try:
                self.display_dir.mkdir(exist_ok=True)
                self.answers_dir.mkdir(exist_ok=True)
                self.votes_dir.mkdir(exist_ok=True)
            except Exception as e:
                print(f"Warning: Failed to create subdirectories, enabling non-blocking mode: {e}")
                self.non_blocking = True

        # File paths
        self.events_log_file = self.session_dir / "events.jsonl"
        self.console_log_file = self.session_dir / "console.log"
        self.system_log_file = self.display_dir / "system.txt"

        # In-memory log storage for real-time access
        self.log_entries: List[LogEntry] = []
        self.agent_logs: Dict[int, List[LogEntry]] = {}

        # MassGen-specific event counters
        self.event_counters = {
            "answer_updates": 0,
            "votes_cast": 0,
            "consensus_reached": 0,
            "debates_started": 0,
            "agent_restarts": 0,
            "notifications_sent": 0,
        }

        # Thread lock for concurrent access
        self._lock = threading.Lock()

        # Initialize logging
        self._setup_logging()

        # Initialize system log file
        if not self.non_blocking:
            self._initialize_system_log()

        # Log session start
        self.log_event(
            "session_started",
            data={
                "session_id": self.session_id,
                "timestamp": time.time(),
                "session_dir": str(self.session_dir),
                "non_blocking_mode": self.non_blocking,
            },
        )

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{timestamp}"

    def _initialize_system_log(self):
        """Initialize the system log file with header."""
        if self.non_blocking:
            return

        try:
            with open(self.system_log_file, "w", encoding="utf-8") as f:
                f.write("MassGen System Messages Log\n")
                f.write(f"Session ID: {self.session_id}\n")
                f.write(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
        except Exception as e:
            print(f"Warning: Failed to initialize system log: {e}")

    def _setup_logging(self):
        """Set up file logging configuration."""
        # Skip file logging setup in non-blocking mode
        if self.non_blocking:
            return

        log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # Ensure log directory exists before creating file handler
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Warning: Failed to create session directory {self.session_dir}, skipping file logging: {e}")
            return

        # Create console log file handler
        console_log_handler = logging.FileHandler(self.console_log_file)
        console_log_handler.setFormatter(log_formatter)
        console_log_handler.setLevel(logging.DEBUG)

        # Add handler to the mass logger
        mass_logger = logging.getLogger("massgen")
        mass_logger.addHandler(console_log_handler)
        mass_logger.setLevel(logging.DEBUG)

        # Prevent duplicate console logs
        mass_logger.propagate = False

        # Add console handler if not already present
        if not any(isinstance(h, logging.StreamHandler) for h in mass_logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(log_formatter)
            console_handler.setLevel(logging.INFO)
            mass_logger.addHandler(console_handler)

    def _format_timestamp(self, timestamp: float) -> str:
        """Format timestamp to human-readable format."""
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def _format_answer_record(self, record: AnswerRecord, agent_id: int) -> str:
        """Format an AnswerRecord into human-readable text."""
        timestamp_str = self._format_timestamp(record.timestamp)

        # Status emoji mapping
        status_emoji = {"working": "🔄", "voted": "✅", "failed": "❌", "unknown": "❓"}
        emoji = status_emoji.get(record.status, "��")

        return f"""
{emoji} UPDATE DETAILS
🕒 Time: {timestamp_str}
📊 Status: {record.status.upper()}
📏 Length: {len(record.answer)} characters

📄 Content:
{record.answer}

{'=' * 80}
"""

    def _format_vote_record(self, record: VoteRecord, agent_id: int) -> str:
        """Format a VoteRecord into human-readable text."""
        timestamp_str = self._format_timestamp(record.timestamp)

        reason_text = record.reason if record.reason else "No reason provided"

        return f"""
🗳️ VOTE CAST
🕒 Time: {timestamp_str}
👤 Voter: Agent {record.voter_id}
🎯 Target: Agent {record.target_id}

📝 Reasoning:
{reason_text}

{'=' * 80}
"""

    def _write_agent_answers(self, agent_id: int, answer_records: List[AnswerRecord]):
        """Write agent's answer history to the answers folder."""
        if self.non_blocking:
            return

        try:
            answers_file = self.answers_dir / f"agent_{agent_id}.txt"

            with open(answers_file, "w", encoding="utf-8") as f:
                # Clean header with useful information
                f.write("=" * 80 + "\n")
                f.write(f"📝 MASSGEN AGENT {agent_id} - ANSWER HISTORY\n")
                f.write("=" * 80 + "\n")
                f.write(f"🆔 Session: {self.session_id}\n")
                f.write(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

                if answer_records:
                    # Calculate some summary statistics
                    total_chars = sum(len(record.answer) for record in answer_records)
                    avg_chars = total_chars / len(answer_records) if answer_records else 0
                    first_update = answer_records[0].timestamp if answer_records else 0
                    last_update = answer_records[-1].timestamp if answer_records else 0
                    duration = last_update - first_update if len(answer_records) > 1 else 0

                    f.write(f"📊 Total Updates: {len(answer_records)}\n")
                    f.write(f"📏 Total Characters: {total_chars:,}\n")
                    f.write(f"📈 Average Length: {avg_chars:.0f} chars\n")
                    if duration > 0:
                        duration_str = f"{duration/60:.1f} minutes" if duration > 60 else f"{duration:.1f} seconds"
                        f.write(f"⏱️ Time Span: {duration_str}\n")
                else:
                    f.write("❌ No answer records found for this agent.\n")

                f.write("=" * 80 + "\n\n")

                if answer_records:
                    for i, record in enumerate(answer_records, 1):
                        # Calculate time elapsed since session start
                        elapsed = record.timestamp - (answer_records[0].timestamp if answer_records else record.timestamp)
                        elapsed_str = f"[+{elapsed/60:.1f}m]" if elapsed > 60 else f"[+{elapsed:.1f}s]"

                        f.write(f"🔢 UPDATE #{i} {elapsed_str}\n")
                        f.write(self._format_answer_record(record, agent_id))
                        f.write("\n")

        except Exception as e:
            print(f"Warning: Failed to write answers for agent {agent_id}: {e}")

    def _write_agent_votes(self, agent_id: int, vote_records: List[VoteRecord]):
        """Write agent's vote history to the votes folder."""
        if self.non_blocking:
            return

        try:
            votes_file = self.votes_dir / f"agent_{agent_id}.txt"

            with open(votes_file, "w", encoding="utf-8") as f:
                # Clean header with useful information
                f.write("=" * 80 + "\n")
                f.write(f"🗳️ MASSGEN AGENT {agent_id} - VOTE HISTORY\n")
                f.write("=" * 80 + "\n")
                f.write(f"🆔 Session: {self.session_id}\n")
                f.write(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

                if vote_records:
                    # Calculate voting statistics
                    vote_targets = {}
                    total_reason_chars = 0
                    for vote in vote_records:
                        vote_targets[vote.target_id] = vote_targets.get(vote.target_id, 0) + 1
                        total_reason_chars += len(vote.reason) if vote.reason else 0

                    most_voted_target = max(vote_targets.items(), key=lambda x: x[1]) if vote_targets else None
                    avg_reason_length = total_reason_chars / len(vote_records) if vote_records else 0

                    first_vote = vote_records[0].timestamp if vote_records else 0
                    last_vote = vote_records[-1].timestamp if vote_records else 0
                    voting_duration = last_vote - first_vote if len(vote_records) > 1 else 0

                    f.write(f"📊 Total Votes Cast: {len(vote_records)}\n")
                    f.write(f"🎯 Unique Targets: {len(vote_targets)}\n")
                    if most_voted_target:
                        f.write(f"👑 Most Voted For: Agent {most_voted_target[0]} ({most_voted_target[1]} votes)\n")
                    f.write(f"📝 Avg Reason Length: {avg_reason_length:.0f} chars\n")
                    if voting_duration > 0:
                        duration_str = f"{voting_duration/60:.1f} minutes" if voting_duration > 60 else f"{voting_duration:.1f} seconds"
                        f.write(f"⏱️ Voting Duration: {duration_str}\n")
                else:
                    f.write("❌ No vote records found for this agent.\n")

                f.write("=" * 80 + "\n\n")

                if vote_records:
                    for i, record in enumerate(vote_records, 1):
                        # Calculate time elapsed since first vote
                        elapsed = record.timestamp - (vote_records[0].timestamp if vote_records else record.timestamp)
                        elapsed_str = f"[+{elapsed/60:.1f}m]" if elapsed > 60 else f"[+{elapsed:.1f}s]"

                        f.write(f"🗳️ VOTE #{i} {elapsed_str}\n")
                        f.write(self._format_vote_record(record, agent_id))
                        f.write("\n")

        except Exception as e:
            print(f"Warning: Failed to write votes for agent {agent_id}: {e}")

    def log_event(
        self,
        event_type: str,
        agent_id: Optional[int] = None,
        phase: str = "unknown",
        data: Optional[Dict[str, Any]] = None,
    ):
        """
        Log a general system event.

        Args:
            event_type: Type of event (e.g., "session_started", "phase_change")
            agent_id: Agent ID if event is agent-specific
            phase: Current system phase
            data: Additional event data
        """
        with self._lock:
            entry = LogEntry(
                timestamp=time.time(),
                event_type=event_type,
                agent_id=agent_id,
                phase=phase,
                data=data or {},
                session_id=self.session_id,
            )

            self.log_entries.append(entry)

            # Also store in agent-specific logs
            if agent_id is not None:
                if agent_id not in self.agent_logs:
                    self.agent_logs[agent_id] = []
                self.agent_logs[agent_id].append(entry)

            # Write to file immediately
            self._write_log_entry(entry)

    def log_agent_answer_update(self, agent_id: int, answer: str, phase: str = "unknown", orchestrator=None):
        """
        Log agent answer update with detailed information and immediately save to file.

        Args:
            agent_id: Agent ID
            answer: Updated answer content
            phase: Current workflow phase
            orchestrator: MassOrchestrator instance to get agent state data
        """
        data = {
            "answer": answer,
            "answer_length": len(answer),
        }

        self.log_event("agent_answer_update", agent_id, phase, data)

        # Immediately write agent answer history to file
        if orchestrator and agent_id in orchestrator.agent_states:
            agent_state = orchestrator.agent_states[agent_id]
            self._write_agent_answers(agent_id, agent_state.updated_answers)

    def log_agent_status_change(self, agent_id: int, old_status: str, new_status: str, phase: str = "unknown"):
        """
        Log agent status change.

        Args:
            agent_id: Agent ID
            old_status: Previous status
            new_status: New status
            phase: Current workflow phase
        """
        data = {
            "old_status": old_status,
            "new_status": new_status,
            "status_change": f"{old_status} {new_status}",
        }

        self.log_event("agent_status_change", agent_id, phase, data)

        # Status changes are captured in system state snapshots

    def log_system_state_snapshot(self, orchestrator, phase: str = "unknown"):
        """
        Log a complete system state snapshot including all agent answers and voting status.

        Args:
            orchestrator: The MassOrchestrator instance
            phase: Current workflow phase
        """

        # Collect all agent states
        agent_states = {}
        all_agent_answers = {}
        vote_records = []

        for agent_id, agent_state in orchestrator.agent_states.items():
            # Full agent state information
            agent_states[agent_id] = {
                "status": agent_state.status,
                "curr_answer": agent_state.curr_answer,
                "vote_target": (agent_state.curr_vote.target_id if agent_state.curr_vote else None),
                "execution_time": agent_state.execution_time,
                "update_count": len(agent_state.updated_answers),
                "seen_updates_timestamps": agent_state.seen_updates_timestamps,
            }

            # Answer history for each agent
            all_agent_answers[agent_id] = {
                "current_answer": agent_state.curr_answer,
                "answer_history": [
                    {
                        "timestamp": update.timestamp,
                        "answer": update.answer,
                        "status": update.status,
                    }
                    for update in agent_state.updated_answers
                ],
            }

        # Collect voting information
        for vote in orchestrator.votes:
            vote_records.append(
                {
                    "voter_id": vote.voter_id,
                    "target_id": vote.target_id,
                    "timestamp": vote.timestamp,
                },
            )

        # Calculate voting status
        vote_counts = Counter(vote.target_id for vote in orchestrator.votes)
        voting_status = {
            "vote_distribution": dict(vote_counts),
            "total_votes_cast": len(orchestrator.votes),
            "total_agents": len(orchestrator.agents),
            "consensus_reached": orchestrator.system_state.consensus_reached,
            "winning_agent_id": orchestrator.system_state.representative_agent_id,
            "votes_needed_for_consensus": max(1, int(len(orchestrator.agents) * orchestrator.consensus_threshold)),
        }

        # Complete system state snapshot
        system_snapshot = {
            "agent_states": agent_states,
            "agent_answers": all_agent_answers,
            "voting_records": vote_records,
            "voting_status": voting_status,
            "system_phase": phase,
            "system_runtime": ((time.time() - orchestrator.system_state.start_time) if orchestrator.system_state.start_time else 0),
        }

        # Log the system snapshot
        self.log_event("system_state_snapshot", phase=phase, data=system_snapshot)

        # Write system state to each agent's log file for complete context
        system_state_entry = {
            "timestamp": time.time(),
            "event": "system_state_snapshot",
            "phase": phase,
            "system_state": system_snapshot,
        }

        # Save individual agent states to answers and votes folders
        for agent_id, agent_state in orchestrator.agent_states.items():
            # Save answer history
            self._write_agent_answers(agent_id, agent_state.updated_answers)

            # Save vote history
            self._write_agent_votes(agent_id, agent_state.cast_votes)

        # Write system state to each agent's display log file for complete context
        for agent_id in orchestrator.agents.keys():
            self._write_agent_display_log(agent_id, system_state_entry)

        return system_snapshot

    def log_voting_event(
        self,
        voter_id: int,
        target_id: int,
        phase: str = "unknown",
        reason: str = "",
        orchestrator=None,
    ):
        """
        Log a voting event with detailed information and immediately save to file.

        Args:
            voter_id: ID of the agent casting the vote
            target_id: ID of the agent being voted for
            phase: Current workflow phase
            reason: Reason for the vote
            orchestrator: MassOrchestrator instance to get agent state data
        """
        with self._lock:
            self.event_counters["votes_cast"] += 1

        data = {
            "voter_id": voter_id,
            "target_id": target_id,
            "reason": reason,
            "total_votes_cast": self.event_counters["votes_cast"],
        }

        self.log_event("voting_event", voter_id, phase, data)

        # Immediately write agent vote history to file
        if orchestrator and voter_id in orchestrator.agent_states:
            agent_state = orchestrator.agent_states[voter_id]
            self._write_agent_votes(voter_id, agent_state.cast_votes)

    def log_consensus_reached(
        self,
        winning_agent_id: int,
        vote_distribution: Dict[int, int],
        is_fallback: bool = False,
        phase: str = "unknown",
    ):
        """
        Log when consensus is reached.

        Args:
            winning_agent_id: ID of the winning agent
            vote_distribution: Dictionary of agent_id -> vote_count
            is_fallback: Whether this was a fallback consensus (timeout)
            phase: Current workflow phase
        """
        with self._lock:
            self.event_counters["consensus_reached"] += 1

        data = {
            "winning_agent_id": winning_agent_id,
            "vote_distribution": vote_distribution,
            "is_fallback": is_fallback,
            "total_consensus_events": self.event_counters["consensus_reached"],
        }

        self.log_event("consensus_reached", winning_agent_id, phase, data)

        # Log to all agent display files
        consensus_entry = {
            "timestamp": time.time(),
            "event": "consensus_reached",
            "phase": phase,
            "winning_agent_id": winning_agent_id,
            "vote_distribution": vote_distribution,
            "is_fallback": is_fallback,
        }
        for agent_id in vote_distribution.keys():
            self._write_agent_display_log(agent_id, consensus_entry)

    def log_phase_transition(self, old_phase: str, new_phase: str, additional_data: Dict[str, Any] = None):
        """
        Log system phase transitions.

        Args:
            old_phase: Previous phase
            new_phase: New phase
            additional_data: Additional context data
        """
        data = {
            "old_phase": old_phase,
            "new_phase": new_phase,
            "phase_transition": f"{old_phase} -> {new_phase}",
            **(additional_data or {}),
        }

        self.log_event("phase_transition", phase=new_phase, data=data)

    def log_notification_sent(
        self,
        agent_id: int,
        notification_type: str,
        content_preview: str,
        phase: str = "unknown",
    ):
        """
        Log when a notification is sent to an agent.

        Args:
            agent_id: Target agent ID
            notification_type: Type of notification (update, debate, presentation, prompt)
            content_preview: Preview of notification content
            phase: Current workflow phase
        """
        with self._lock:
            self.event_counters["notifications_sent"] += 1

        data = {
            "notification_type": notification_type,
            "content_preview": (content_preview[:200] + "..." if len(content_preview) > 200 else content_preview),
            "content_length": len(content_preview),
            "total_notifications_sent": self.event_counters["notifications_sent"],
        }

        self.log_event("notification_sent", agent_id, phase, data)

        # Log to agent display file
        notification_entry = {
            "timestamp": time.time(),
            "event": "notification_received",
            "phase": phase,
            "notification_type": notification_type,
            "content": content_preview,
        }
        self._write_agent_display_log(agent_id, notification_entry)

    def log_agent_restart(self, agent_id: int, reason: str, phase: str = "unknown"):
        """
        Log when an agent is restarted.

        Args:
            agent_id: ID of the restarted agent
            reason: Reason for restart
            phase: Current workflow phase
        """
        with self._lock:
            self.event_counters["agent_restarts"] += 1

        data = {
            "restart_reason": reason,
            "total_restarts": self.event_counters["agent_restarts"],
        }

        self.log_event("agent_restart", agent_id, phase, data)

        # Log to agent display file
        restart_entry = {
            "timestamp": time.time(),
            "event": "agent_restarted",
            "phase": phase,
            "reason": reason,
        }
        self._write_agent_display_log(agent_id, restart_entry)

    def log_debate_started(self, phase: str = "unknown"):
        """
        Log when a debate phase starts.

        Args:
            phase: Current workflow phase
        """
        with self._lock:
            self.event_counters["debates_started"] += 1

        data = {"total_debates": self.event_counters["debates_started"]}

        self.log_event("debate_started", phase=phase, data=data)

    def log_task_completion(self, final_solution: Dict[str, Any]):
        """
        Log task completion with final results.

        Args:
            final_solution: Complete final solution data
        """
        data = {"final_solution": final_solution, "completion_timestamp": time.time()}

        self.log_event("task_completed", phase="completed", data=data)

    def _write_log_entry(self, entry: LogEntry):
        """Write a single log entry to the session JSONL file."""
        # Skip file operations in non-blocking mode
        if self.non_blocking:
            return

        try:
            # Create directory if it doesn't exist
            self.events_log_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.events_log_file, "a", buffering=1) as f:  # Line buffering
                json_line = json.dumps(entry.to_dict(), default=str, ensure_ascii=False)
                f.write(json_line + "\n")
                f.flush()
        except Exception as e:
            print(f"Warning: Failed to write log entry: {e}")

    def _write_agent_display_log(self, agent_id: int, data: Dict[str, Any]):
        """Write agent-specific display log entry."""
        # Skip file operations in non-blocking mode
        if self.non_blocking:
            return

        try:
            agent_log_file = self.display_dir / f"agent_{agent_id}.txt"

            # Create directory if it doesn't exist
            agent_log_file.parent.mkdir(parents=True, exist_ok=True)

            # Initialize file if it doesn't exist
            if not agent_log_file.exists():
                with open(agent_log_file, "w", encoding="utf-8") as f:
                    f.write(f"MassGen Agent {agent_id} Display Log\n")
                    f.write(f"Session: {self.session_id}\n")
                    f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 80 + "\n\n")

            # Write event entry
            with open(agent_log_file, "a", encoding="utf-8") as f:
                timestamp_str = self._format_timestamp(data.get("timestamp", time.time()))
                f.write(f"[{timestamp_str}] {data.get('event', 'unknown_event')}\n")

                # Write event details
                for key, value in data.items():
                    if key not in ["timestamp", "event"]:
                        f.write(f"  {key}: {value}\n")
                f.write("\n")
                f.flush()
        except Exception as e:
            print(f"Warning: Failed to write agent display log: {e}")

    def _write_system_log(self, message: str):
        """Write a system message to the system log file."""
        if self.non_blocking:
            return

        try:
            with open(self.system_log_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%H:%M:%S")
                f.write(f"[{timestamp}] {message}\n")
                f.flush()  # Ensure immediate write
        except Exception as e:
            print(f"Error writing to system log: {e}")

    def get_agent_history(self, agent_id: int) -> List[LogEntry]:
        """Get complete history for a specific agent."""
        with self._lock:
            return self.agent_logs.get(agent_id, []).copy()

    def get_session_summary(self) -> Dict[str, Any]:
        """Get comprehensive session summary."""
        with self._lock:
            # Count events by type
            event_counts = {}
            agent_activities = {}

            for entry in self.log_entries:
                # Count events
                event_counts[entry.event_type] = event_counts.get(entry.event_type, 0) + 1

                # Count agent activities
                if entry.agent_id is not None:
                    agent_id = entry.agent_id
                    if agent_id not in agent_activities:
                        agent_activities[agent_id] = []
                    agent_activities[agent_id].append(
                        {
                            "timestamp": entry.timestamp,
                            "event_type": entry.event_type,
                            "phase": entry.phase,
                        },
                    )

            return {
                "session_id": self.session_id,
                "total_events": len(self.log_entries),
                "event_counts": event_counts,
                "agents_involved": list(agent_activities.keys()),
                "agent_activities": agent_activities,
                "session_duration": self._calculate_session_duration(),
                "log_files": {
                    "session_dir": str(self.session_dir),
                    "events_log": str(self.events_log_file),
                    "console_log": str(self.console_log_file),
                    "display_dir": str(self.display_dir),
                    "answers_dir": str(self.answers_dir),
                    "votes_dir": str(self.votes_dir),
                },
            }

    def _calculate_session_duration(self) -> float:
        """Calculate total session duration."""
        if not self.log_entries:
            return 0.0

        start_time = min(entry.timestamp for entry in self.log_entries)
        end_time = max(entry.timestamp for entry in self.log_entries)
        return end_time - start_time

    def save_agent_states(self, orchestrator):
        """Save current agent states to answers and votes folders."""
        if self.non_blocking:
            return

        try:
            for agent_id, agent_state in orchestrator.agent_states.items():
                # Save answer history
                self._write_agent_answers(agent_id, agent_state.updated_answers)

                # Save vote history
                self._write_agent_votes(agent_id, agent_state.cast_votes)
        except Exception as e:
            print(f"Warning: Failed to save agent states: {e}")

    def cleanup(self):
        """Clean up and finalize the logging session."""
        self.log_event(
            "session_ended",
            data={
                "end_timestamp": time.time(),
                "total_events_logged": len(self.log_entries),
            },
        )

    def get_session_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive session statistics.

        Returns:
            Dictionary containing session metrics and statistics
        """
        with self._lock:
            total_events = len(self.log_entries)
            agent_event_counts = {}

            for agent_id, logs in self.agent_logs.items():
                agent_event_counts[agent_id] = len(logs)

            return {
                "session_id": self.session_id,
                "total_events": total_events,
                "event_counters": self.event_counters.copy(),
                "agent_event_counts": agent_event_counts,
                "total_agents": len(self.agent_logs),
                "session_duration": time.time() - (self.log_entries[0].timestamp if self.log_entries else time.time()),
            }


# Global log manager instance
_log_manager: Optional[MassLogManager] = None


def initialize_logging(log_dir: str = "logs", session_id: Optional[str] = None, non_blocking: bool = False) -> MassLogManager:
    """Initialize the global logging system."""
    global _log_manager

    # Check environment variable for non-blocking mode
    env_non_blocking = os.getenv("MassGen_NON_BLOCKING_LOGGING", "").lower() in (
        "true",
        "1",
        "yes",
    )
    if env_non_blocking:
        print("🔧 MassGen_NON_BLOCKING_LOGGING environment variable detected - enabling non-blocking mode")
        non_blocking = True

    _log_manager = MassLogManager(log_dir, session_id, non_blocking)
    return _log_manager


def get_log_manager() -> Optional[MassLogManager]:
    """Get the current log manager instance."""
    return _log_manager


def cleanup_logging():
    """Cleanup the global logging system."""
    global _log_manager
    if _log_manager:
        _log_manager.cleanup()
        _log_manager = None
