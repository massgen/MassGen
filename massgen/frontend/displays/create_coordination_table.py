#!/usr/bin/env python3
"""
Multi-Agent Coordination Event Table Generator

Parses coordination_events.json and generates a formatted table showing
the progression of agent interactions across rounds.
"""

import json
import sys
from typing import Dict, List, Any, Optional, Set, Union
from dataclasses import dataclass, field
from collections import defaultdict
import textwrap

try:
    from rich.table import Table
    from rich.console import Console
    from rich.text import Text
    from rich import box

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


@dataclass
class AgentState:
    """Track state for a single agent"""

    status: str = "idle"
    current_answer: Optional[str] = None
    answer_preview: Optional[str] = None
    vote: Optional[str] = None
    vote_reason: Optional[str] = None
    context: List[str] = field(default_factory=list)
    round: int = 0
    is_final: bool = False
    has_final_answer: bool = False
    is_selected_winner: bool = False
    has_voted: bool = False  # Track if agent has already voted


@dataclass
class RoundData:
    """Data for a single round"""

    round_num: int
    round_type: str  # "R0", "R1", "R2", ... "FINAL"
    agent_states: Dict[str, AgentState]


class CoordinationTableBuilder:
    def __init__(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]):
        # Handle both old format (list of events) and new format (dict with metadata)
        if isinstance(data, dict) and "events" in data:
            self.events = data["events"]
            self.session_metadata = data.get("session_metadata", {})
        else:
            self.events = data if isinstance(data, list) else []
            self.session_metadata = {}

        self.agents = self._extract_agents()
        self.agent_mapping = self._create_agent_mapping()
        self.agent_answers = self._extract_answer_previews()
        self.final_winner = self._find_final_winner()
        self.final_round_num = self._find_final_round_number()
        self.agent_vote_rounds = self._track_vote_rounds()
        self.rounds = self._process_events()
        self.user_question = self._extract_user_question()

    def _extract_agents(self) -> List[str]:
        """Extract unique agent IDs from events"""
        agents = set()
        for event in self.events:
            agent_id = event.get("agent_id")
            if agent_id and agent_id not in [None, "null"]:
                agents.add(agent_id)
        return sorted(list(agents))

    def _create_agent_mapping(self) -> Dict[str, str]:
        """Create explicit mapping from agent_id to agent_number for answer labels"""
        mapping = {}
        for i, agent_id in enumerate(self.agents, 1):
            mapping[agent_id] = str(i)
        return mapping

    def _extract_user_question(self) -> str:
        """Extract the user question from session metadata"""
        return self.session_metadata.get("user_prompt", "No user prompt found")

    def _extract_answer_previews(self) -> Dict[str, str]:
        """Extract the actual answer text for each agent using explicit mapping"""
        answers = {}

        # Try to get from final_agent_selected event
        for event in self.events:
            if event["event_type"] == "final_agent_selected":
                context = event.get("context", {})
                answers_for_context = context.get("answers_for_context", {})

                # Map answers to agents using explicit agent mapping
                for label, answer in answers_for_context.items():
                    # Direct match: label is an agent_id
                    if label in self.agents:
                        answers[label] = answer
                    else:
                        # Map answer label to agent using our explicit mapping
                        # For labels like "agent1.1", extract the number and find matching agent
                        if label.startswith("agent") and "." in label:
                            try:
                                # Extract agent number from label (e.g., "agent1.1" -> "1")
                                agent_num = label.split(".")[0][5:]  # Remove "agent" prefix
                                # Find agent with this number in our mapping
                                for agent_id, mapped_num in self.agent_mapping.items():
                                    if mapped_num == agent_num:
                                        answers[agent_id] = answer
                                        break
                            except (IndexError, ValueError):
                                continue

        return answers

    def _find_final_winner(self) -> Optional[str]:
        """Find which agent was selected as the final winner"""
        for event in self.events:
            if event["event_type"] == "final_agent_selected":
                return event.get("agent_id")
        return None

    def _find_final_round_number(self) -> Optional[int]:
        """Find which round number is the final round"""
        for event in self.events:
            if event["event_type"] == "final_round_start":
                context = event.get("context", {})
                return context.get("round", context.get("final_round"))

        # If no explicit final round, check for final_answer events
        for event in self.events:
            if event["event_type"] == "final_answer":
                context = event.get("context", {})
                return context.get("round")

        return None

    def _track_vote_rounds(self) -> Dict[str, int]:
        """Track which round each agent cast their vote"""
        vote_rounds = {}
        for event in self.events:
            if event["event_type"] == "vote_cast":
                agent_id = event.get("agent_id")
                context = event.get("context", {})
                round_num = context.get("round", 0)
                if agent_id:
                    vote_rounds[agent_id] = round_num
        return vote_rounds

    def _process_events(self) -> List[RoundData]:
        """Process events into rounds with proper organization"""
        # Find all unique rounds
        all_rounds = set()
        for event in self.events:
            context = event.get("context", {})
            round_num = context.get("round", 0)
            all_rounds.add(round_num)

        # Exclude final round from regular rounds if it exists
        regular_rounds = sorted(
            all_rounds - {self.final_round_num} if self.final_round_num else all_rounds
        )

        # Initialize round states
        rounds = {}
        for r in regular_rounds:
            rounds[r] = {agent: AgentState(round=r) for agent in self.agents}

        # Add final round if exists
        if self.final_round_num is not None:
            rounds[self.final_round_num] = {
                agent: AgentState(round=self.final_round_num) for agent in self.agents
            }

        # Process events
        for event in self.events:
            event_type = event["event_type"]
            agent_id = event.get("agent_id")
            context = event.get("context", {})

            if agent_id and agent_id in self.agents:
                # Determine the round for this event
                round_num = context.get("round", 0)

                # Special handling for votes and answers that specify rounds
                if event_type == "vote_cast":
                    round_num = context.get("round", 0)
                elif event_type == "new_answer":
                    round_num = context.get("round", 0)
                elif event_type == "restart_completed":
                    round_num = context.get("agent_round", context.get("round", 0))
                elif event_type == "final_answer":
                    round_num = (
                        self.final_round_num
                        if self.final_round_num
                        else context.get("round", 0)
                    )

                if round_num in rounds:
                    agent_state = rounds[round_num][agent_id]

                    if event_type == "context_received":
                        labels = context.get("available_answer_labels", [])
                        agent_state.context = labels

                    elif event_type == "new_answer":
                        label = context.get("label")
                        if label:
                            agent_state.current_answer = label
                            # Get preview from saved answers
                            if agent_id in self.agent_answers:
                                agent_state.answer_preview = self.agent_answers[
                                    agent_id
                                ]

                    elif event_type == "vote_cast":
                        agent_state.vote = context.get("voted_for_label")
                        agent_state.vote_reason = context.get("reason")
                        agent_state.has_voted = True

                    elif event_type == "final_answer":
                        agent_state.has_final_answer = True
                        label = context.get("label")
                        agent_state.current_answer = f"Final answer provided ({label})"
                        agent_state.is_final = True
                        # Try to get the actual answer content if available
                        if agent_id in self.agent_answers:
                            agent_state.answer_preview = self.agent_answers[agent_id]
                            agent_state.current_answer = self.agent_answers[agent_id]

                    elif event_type == "final_agent_selected":
                        agent_state.is_selected_winner = True

                    elif event_type == "status_change":
                        status = event.get("details", "").replace(
                            "Changed to status: ", ""
                        )
                        agent_state.status = status

        # Mark non-winner as completed in FINAL round
        if self.final_winner and self.final_round_num in rounds:
            for agent in self.agents:
                if agent != self.final_winner:
                    rounds[self.final_round_num][agent].status = "completed"

        # Build final round list
        round_list = []

        # Add regular rounds
        for r in regular_rounds:
            round_type = f"R{r}"
            round_list.append(
                RoundData(
                    r,
                    round_type,
                    rounds.get(r, {agent: AgentState() for agent in self.agents}),
                )
            )

        # Add FINAL round if exists
        if self.final_round_num is not None and self.final_round_num in rounds:
            round_list.append(
                RoundData(self.final_round_num, "FINAL", rounds[self.final_round_num])
            )

        return round_list

    def _format_cell(self, content: str, width: int) -> str:
        """Format content to fit within cell width, centered"""
        if not content:
            return " " * width

        if len(content) <= width:
            return content.center(width)
        else:
            # Truncate if too long
            truncated = content[: width - 3] + "..."
            return truncated.center(width)

    def _build_agent_cell_content(
        self, agent_state: AgentState, round_type: str, agent_id: str, round_num: int
    ) -> List[str]:
        """Build the content for an agent's cell in a round"""
        lines = []

        # Determine if we should show context (but not for voting agents)
        # Show context only if agent is doing something meaningful with it (but not voting)
        show_context = (
            (agent_state.current_answer and not agent_state.vote)
            or agent_state.has_final_answer  # Agent answered (but didn't vote)
            or agent_state.status  # Agent has final answer
            in ["streaming", "answering"]  # Agent is actively working
        )

        # Don't show context for completed agents in FINAL round
        if round_type == "FINAL" and agent_state.status == "completed":
            show_context = False

        # Add context if appropriate
        if show_context:
            if agent_state.context:
                context_str = f"Context: [{', '.join(agent_state.context)}]"
            else:
                context_str = "Context: []"
            lines.append(context_str)

        # Add content based on what happened in this round
        # Check for votes first, regardless of round type
        if agent_state.vote:
            # Agent voted in this round - show Context first, then vote
            if agent_state.context:
                lines.append(f"Context: [{', '.join(agent_state.context)}]")
            lines.append(f"VOTE: {agent_state.vote}")
            if agent_state.vote_reason:
                reason = (
                    agent_state.vote_reason[:47] + "..."
                    if len(agent_state.vote_reason) > 50
                    else agent_state.vote_reason
                )
                lines.append(f"Reason: {reason}")

        elif round_type == "FINAL":
            # Final presentation round
            if agent_state.has_final_answer:
                lines.append(f"FINAL ANSWER: {agent_state.current_answer}")
                if agent_state.answer_preview:
                    clean_preview = agent_state.answer_preview.replace(
                        "\n", " "
                    ).strip()
                    lines.append(f"Preview: {clean_preview}")
                else:
                    lines.append("Preview: [Answer not available]")
            elif agent_state.status == "completed":
                lines.append("(completed)")
            else:
                lines.append("(waiting)")

        elif agent_state.current_answer and not agent_state.vote:
            # Agent provided an answer in this round
            lines.append(f"NEW ANSWER: {agent_state.current_answer}")
            if agent_state.answer_preview:
                clean_preview = agent_state.answer_preview.replace("\n", " ").strip()
                lines.append(f"Preview: {clean_preview}")
            else:
                lines.append("Preview: [Answer not available]")

        elif agent_state.status in ["streaming", "answering"]:
            lines.append("(answering)")

        elif agent_state.status == "voted":
            lines.append("(voted)")

        elif agent_state.status == "answered":
            lines.append("(answered)")

        else:
            lines.append("(waiting)")

        return lines

    def generate_event_table(self) -> str:
        """Generate an event-driven formatted table"""
        num_agents = len(self.agents)
        # Dynamic cell width based on number of agents
        if num_agents <= 2:
            cell_width = 60
        elif num_agents == 3:
            cell_width = 40
        elif num_agents == 4:
            cell_width = 30
        else:  # 5+ agents
            cell_width = 25
        total_width = 10 + (cell_width + 1) * num_agents + 1

        lines = []

        # Helper function to add separator
        def add_separator(style="-"):
            lines.append(
                "|" + style * 10 + "+" + (style * cell_width + "+") * num_agents
            )

        # Add legend/explanation section
        lines.extend(self._create_legend_section(cell_width))

        # Top border
        lines.append("+" + "-" * (total_width - 2) + "+")

        # Header row
        header = "|   Event  |"
        for agent in self.agents:
            # Use format "Agent 1 (full_agent_id)"
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num} ({agent})"
            header += self._format_cell(agent_name, cell_width) + "|"
        lines.append(header)

        # Header separator
        lines.append("|" + "-" * 10 + "+" + ("-" * cell_width + "+") * num_agents)

        # User question row
        question_row = "|   USER   |"
        question_width = cell_width * num_agents + (num_agents - 1)
        question_text = self.user_question.center(question_width)
        question_row += question_text + "|"
        lines.append(question_row)

        # Double separator
        lines.append("|" + "=" * 10 + "+" + ("=" * cell_width + "+") * num_agents)

        # Process events chronologically
        agent_states = {
            agent: {
                "status": "idle",
                "context": [],
                "answer": None,
                "vote": None,
                "preview": None,
                "last_streaming_logged": False,
            }
            for agent in self.agents
        }
        event_num = 1

        for event in self.events:
            event_type = event["event_type"]
            agent_id = event.get("agent_id")
            context = event.get("context", {})

            # Skip session-level events - just show the actual coordination work

            # Skip iteration_start events - we already have session_start

            # Skip system-level events without agent_id
            if not agent_id or agent_id not in self.agents:
                continue

            # Update agent state and create table row
            row_added = False

            if event_type == "status_change":
                status = event.get("details", "").replace("Changed to status: ", "")
                old_status = agent_states[agent_id]["status"]
                agent_states[agent_id]["status"] = status

                # Only log the FIRST streaming status for each agent, not repetitive ones
                if status in ["streaming", "answering"]:
                    # Skip streaming that happens after voting - we'll show final_answer directly
                    if old_status == "voted":
                        # Just update status but don't show this event
                        pass
                    else:
                        # Only show if this is a meaningful transition (not streaming -> streaming)
                        if (
                            old_status not in ["streaming", "answering"]
                            or not agent_states[agent_id]["last_streaming_logged"]
                        ):
                            # Create multi-line event with context and streaming start
                            event_lines = []
                            # Show context when starting to stream
                            if agent_states[agent_id]["context"]:
                                event_lines.append(
                                    f"📋 Context: [{', '.join(agent_states[agent_id]['context'])}]"
                                )
                            else:
                                event_lines.append(f"📋 Context: []")
                            event_lines.append(f"💭 Started {status}")

                            lines.extend(
                                self._create_multi_line_event_row(
                                    event_num,
                                    agent_id,
                                    event_lines,
                                    agent_states,
                                    cell_width,
                                )
                            )
                            add_separator("-")  # Add separator after event
                            agent_states[agent_id]["last_streaming_logged"] = True
                            event_num += 1
                            row_added = True
                elif status not in ["streaming", "answering"]:
                    # Reset the flag when status changes to something else
                    agent_states[agent_id]["last_streaming_logged"] = False

            elif event_type == "context_received":
                labels = context.get("available_answer_labels", [])
                agent_states[agent_id]["context"] = labels
                # Don't create a separate row for context, it will be shown with answers/votes

            elif event_type == "restart_triggered":
                # Show restart trigger event spanning both columns (it's a coordination event)
                agent_num = self.agent_mapping.get(agent_id, "?")
                agent_name = f"Agent {agent_num}"
                lines.extend(
                    self._create_system_row(
                        f"🔁 {agent_name} RESTART TRIGGERED", cell_width
                    )
                )
                event_num += 1

            elif event_type == "restart_completed":
                # Show restart completion
                agent_round = context.get("agent_round", context.get("round", 0))
                lines.extend(
                    self._create_event_row(
                        event_num,
                        agent_id,
                        f"✅ RESTART COMPLETED (Restart {agent_round})",
                        agent_states,
                        cell_width,
                    )
                )
                add_separator("-")
                event_num += 1
                # Reset streaming flag so next streaming will be shown
                agent_states[agent_id]["last_streaming_logged"] = False

            elif event_type == "new_answer":
                label = context.get("label")
                if label:
                    agent_states[agent_id]["answer"] = label
                    agent_states[agent_id]["status"] = "answered"
                    agent_states[agent_id][
                        "last_streaming_logged"
                    ] = False  # Reset for next round
                    # Get preview from saved answers
                    preview = ""
                    if agent_id in self.agent_answers:
                        preview = self.agent_answers[agent_id]
                        agent_states[agent_id]["preview"] = preview

                    # Create multi-line event with answer and preview
                    event_lines = []
                    # Context already shown when streaming started
                    event_lines.append(f"✨ NEW ANSWER: {label}")
                    if preview:
                        clean_preview = preview.replace("\n", " ").strip()
                        event_lines.append(f"👁️  Preview: {clean_preview}")

                    lines.extend(
                        self._create_multi_line_event_row(
                            event_num, agent_id, event_lines, agent_states, cell_width
                        )
                    )
                    add_separator("-")  # Add separator after event
                    event_num += 1
                    row_added = True

            elif event_type == "vote_cast":
                vote = context.get("voted_for_label")
                reason = context.get("reason", "")
                if vote:
                    agent_states[agent_id]["vote"] = vote
                    agent_states[agent_id]["status"] = "voted"
                    agent_states[agent_id][
                        "last_streaming_logged"
                    ] = False  # Reset for next round

                    # Create multi-line event with vote and reason
                    event_lines = []
                    # Context already shown when streaming started
                    event_lines.append(f"🗳️  VOTE: {vote}")
                    if reason:
                        clean_reason = reason.replace("\n", " ").strip()
                        reason_str = (
                            clean_reason[:50] + "..."
                            if len(clean_reason) > 50
                            else clean_reason
                        )
                        event_lines.append(f"💭 Reason: {reason_str}")

                    lines.extend(
                        self._create_multi_line_event_row(
                            event_num, agent_id, event_lines, agent_states, cell_width
                        )
                    )
                    add_separator("-")  # Add separator after event
                    event_num += 1
                    row_added = True

            elif event_type == "final_agent_selected":
                # Show winner selection
                winner_name = "Agent1" if "1" in agent_id else "Agent2"
                lines.extend(
                    self._create_system_row(
                        f"🏆 {winner_name} selected as winner", cell_width
                    )
                )
                # Update other agents to completed status
                for other_agent in self.agents:
                    if other_agent != agent_id:
                        agent_states[other_agent]["status"] = "completed"

            elif event_type == "final_answer":
                label = context.get("label")
                if label:
                    agent_states[agent_id]["status"] = "final"

                    # Ensure preview is available for final answer
                    if not agent_states[agent_id]["preview"] and agent_id in self.agent_answers:
                        agent_states[agent_id]["preview"] = self.agent_answers[agent_id]

                    # Create multi-line event with final answer
                    event_lines = []
                    # Context already shown when streaming started
                    event_lines.append(f"🎯 FINAL ANSWER: {label}")
                    if agent_states[agent_id]["preview"]:
                        clean_preview = (
                            agent_states[agent_id]["preview"].replace("\n", " ").strip()
                        )
                        event_lines.append(f"👁️  Preview: {clean_preview}")

                    lines.extend(
                        self._create_multi_line_event_row(
                            event_num, agent_id, event_lines, agent_states, cell_width
                        )
                    )
                    add_separator("-")  # Add separator after event
                    event_num += 1
                    row_added = True

        # Add summary statistics
        lines.extend(self._create_summary_section(agent_states, cell_width))

        # Bottom border
        lines.append("+" + "-" * (total_width - 2) + "+")

        return "\n".join(lines)

    def _create_event_row(
        self,
        event_num: int,
        active_agent: str,
        event_description: str,
        agent_states: dict,
        cell_width: int,
    ) -> list:
        """Create a table row for a single event"""
        row = "|"

        # Event number
        event_label = f"    E{event_num}   "
        row += event_label[-10:].rjust(10) + "|"

        # Agent cells
        for agent in self.agents:
            if agent == active_agent:
                # This agent is performing the event
                cell_content = event_description
            else:
                # Show current status for other agents - prioritize active states
                status = agent_states[agent]["status"]
                if status in ["streaming", "answering"]:
                    cell_content = f"🔄 ({status})"
                elif status == "voted":
                    # Just show voted status without the value to avoid confusion
                    cell_content = "✅ (voted)"
                elif status == "answered":
                    if agent_states[agent]["answer"]:
                        cell_content = f"✅ Answered: {agent_states[agent]['answer']}"
                    else:
                        cell_content = "✅ (answered)"
                elif status == "completed":
                    cell_content = "✅ (completed)"
                elif status == "final":
                    cell_content = "🎯 (final answer given)"
                elif status == "idle":
                    cell_content = "⏳ (waiting)"
                else:
                    cell_content = f"({status})"

            row += self._format_cell(cell_content, cell_width) + "|"

        return [row]

    def _create_multi_line_event_row(
        self,
        event_num: int,
        active_agent: str,
        event_lines: list,
        agent_states: dict,
        cell_width: int,
    ) -> list:
        """Create multiple table rows for a single event with multiple lines of content"""
        rows = []

        for line_idx, event_line in enumerate(event_lines):
            row = "|"

            # Event number (only on first line)
            if line_idx == 0:
                event_label = f"    E{event_num}   "
                row += event_label[-10:].rjust(10) + "|"
            else:
                row += " " * 10 + "|"

            # Agent cells
            for agent in self.agents:
                if agent == active_agent:
                    # This agent is performing the event
                    cell_content = event_line
                else:
                    # Show current status for other agents (only on first line) - prioritize active states
                    if line_idx == 0:
                        status = agent_states[agent]["status"]
                        if status in ["streaming", "answering"]:
                            cell_content = f"🔄 ({status})"
                        elif status == "voted":
                            # Just show voted status without the value to avoid confusion
                            cell_content = "✅ (voted)"
                        elif status == "answered":
                            if agent_states[agent]["answer"]:
                                cell_content = (
                                    f"✅ Answered: {agent_states[agent]['answer']}"
                                )
                            else:
                                cell_content = "✅ (answered)"
                        elif status == "completed":
                            cell_content = "✅ (completed)"
                        elif status == "final":
                            cell_content = "🎯 (final answer given)"
                        elif status == "idle":
                            cell_content = "⏳ (waiting)"
                        else:
                            cell_content = f"({status})"
                    else:
                        cell_content = ""

                row += self._format_cell(cell_content, cell_width) + "|"

            rows.append(row)

        return rows

    def _create_system_row(self, message: str, cell_width: int) -> list:
        """Create a system announcement row that spans all columns"""
        total_width = 10 + (cell_width + 1) * len(self.agents) + 1

        # Separator line
        separator = "|" + "-" * 10 + "+" + ("-" * cell_width + "+") * len(self.agents)

        # Message row
        message_width = total_width - 3  # Account for borders
        message_row = "|" + message.center(message_width) + "|"

        # Another separator
        separator2 = "|" + "-" * 10 + "+" + ("-" * cell_width + "+") * len(self.agents)

        return [separator, message_row, separator2]

    def _create_summary_section(self, agent_states: dict, cell_width: int) -> list:
        """Create summary statistics section"""
        lines = []

        # Calculate statistics
        total_answers = sum(1 for agent in self.agents if agent_states[agent]["answer"])
        total_votes = sum(1 for agent in self.agents if agent_states[agent]["vote"])
        total_restarts = len(
            [e for e in self.events if e["event_type"] == "restart_completed"]
        )

        # Count per-agent stats
        agent_stats = {}
        for agent in self.agents:
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num}"
            agent_stats[agent_name] = {
                "answers": 1 if agent_states[agent]["answer"] else 0,
                "votes": 1 if agent_states[agent]["vote"] else 0,
                "final_status": agent_states[agent]["status"],
            }

        # Count restarts per agent
        for event in self.events:
            if (
                event["event_type"] == "restart_completed"
                and event.get("agent_id") in self.agents
            ):
                agent_id = event["agent_id"]
                agent_num = self.agent_mapping.get(agent_id, "?")
                agent_name = f"Agent {agent_num}"
                if agent_name not in agent_stats:
                    agent_stats[agent_name] = {"restarts": 0}
                if "restarts" not in agent_stats[agent_name]:
                    agent_stats[agent_name]["restarts"] = 0
                agent_stats[agent_name]["restarts"] += 1

        # Create separator
        separator = "|" + "=" * 10 + "+" + ("=" * cell_width + "+") * len(self.agents)
        lines.append(separator)

        # Summary header
        summary_header = "|  SUMMARY |"
        for agent in self.agents:
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num}"
            summary_header += self._format_cell(agent_name, cell_width) + "|"
        lines.append(summary_header)

        # Separator
        lines.append("|" + "-" * 10 + "+" + ("-" * cell_width + "+") * len(self.agents))

        # Answers row
        answers_row = "| Answers  |"
        for agent in self.agents:
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num}"
            count = agent_stats.get(agent_name, {}).get("answers", 0)
            answers_row += (
                self._format_cell(
                    f"{count} answer{'s' if count != 1 else ''}", cell_width
                )
                + "|"
            )
        lines.append(answers_row)

        # Votes row
        votes_row = "| Votes    |"
        for agent in self.agents:
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num}"
            count = agent_stats.get(agent_name, {}).get("votes", 0)
            votes_row += (
                self._format_cell(
                    f"{count} vote{'s' if count != 1 else ''}", cell_width
                )
                + "|"
            )
        lines.append(votes_row)

        # Restarts row
        restarts_row = "| Restarts |"
        for agent in self.agents:
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num}"
            count = agent_stats.get(agent_name, {}).get("restarts", 0)
            restarts_row += (
                self._format_cell(
                    f"{count} restart{'s' if count != 1 else ''}", cell_width
                )
                + "|"
            )
        lines.append(restarts_row)

        # Final status row
        status_row = "| Status   |"
        for agent in self.agents:
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num}"
            status = agent_states[agent]["status"]
            if status == "final":
                display = "🏆 Winner"
            elif status == "completed":
                display = "✅ Completed"
            elif status == "voted":
                display = "✅ Voted"
            else:
                display = f"({status})"
            status_row += self._format_cell(display, cell_width) + "|"
        lines.append(status_row)

        # Overall totals row
        lines.append("|" + "-" * 10 + "+" + ("-" * cell_width + "+") * len(self.agents))
        totals_row = "| TOTALS   |"
        total_width = cell_width * len(self.agents) + (len(self.agents) - 1)
        totals_content = (
            f"{total_answers} answers, {total_votes} votes, {total_restarts} restarts"
        )
        winner_name = None
        for agent in self.agents:
            if agent_states[agent]["status"] == "final":
                winner_name = f"Agent{agent.split('_')[-1]}" if "_" in agent else agent
                break
        if winner_name:
            totals_content += f" → {winner_name} selected"
        totals_row += totals_content.center(total_width) + "|"
        lines.append(totals_row)

        return lines

    def _get_legend_content(self) -> dict:
        """Get legend content as structured data to be formatted by different displays"""
        return {
            "event_symbols": [
                ("💭 Started streaming", "Agent begins thinking/processing"),
                ("✨ NEW ANSWER", "Agent provides a labeled answer"),
                ("🗳️  VOTE", "Agent votes for an answer"),
                ("💭 Reason", "Reasoning behind the vote"),
                ("👁️  Preview", "Content of the answer"),
                ("🔁 RESTART TRIGGERED", "Agent requests to restart"),
                ("✅ RESTART COMPLETED", "Agent finishes restart"),
                ("🎯 FINAL ANSWER", "Winner provides final response"),
                ("🏆 Winner selected", "System announces winner"),
            ],
            "status_symbols": [
                ("💭 (streaming)", "Currently thinking/processing"),
                ("⏳ (waiting)", "Idle, waiting for turn"),
                ("✅ (answered)", "Has provided an answer"),
                ("✅ (voted)", "Has cast a vote"),
                ("✅ (completed)", "Task completed"),
                ("🎯 (final answer given)", "Winner completed final answer"),
            ],
            "terms": [
                ("Context", "Available answer options agent can see"),
                ("Restart", "Agent starts over (clears memory)"),
                ("Event", "Chronological action in the coordination"),
                (
                    "Answer Labels",
                    "Each answer gets a unique ID (agent1.1, agent2.1, etc.)\n                  Format: agent{N}.{attempt} where N=agent number, attempt=new answer number\n                  Example: agent1.1 = Agent1's 1st answer, agent2.1 = Agent2's 1st answer",
                ),
                ("agent1.final", "Special label for the winner's final answer"),
            ],
        }

    def _create_legend_section(self, cell_width: int) -> list:
        """Create legend/explanation section at the top for plain text"""
        lines = []
        legend_data = self._get_legend_content()

        # Title
        lines.append("")
        lines.append("Multi-Agent Coordination Events Log")
        lines.append("=" * 50)
        lines.append("")

        # Event symbols
        lines.append("📋 EVENT SYMBOLS:")
        for symbol, description in legend_data["event_symbols"]:
            # Pad symbol to consistent width (24 chars) for alignment
            padded = f"  {symbol}".ljust(28)
            lines.append(f"{padded}- {description}")
        lines.append("")

        # Status symbols
        lines.append("📊 STATUS SYMBOLS:")
        for symbol, description in legend_data["status_symbols"]:
            padded = f"  {symbol}".ljust(28)
            lines.append(f"{padded}- {description}")
        lines.append("")

        # Terms
        lines.append("📖 TERMS:")
        for term, description in legend_data["terms"]:
            if "\n" in description:
                # Handle multi-line descriptions
                first_line = description.split("\n")[0]
                lines.append(f"  {term.ljust(13)} - {first_line}")
                for line in description.split("\n")[1:]:
                    lines.append(f"  {line}")
            else:
                lines.append(f"  {term.ljust(13)} - {description}")
        lines.append("")

        return lines

    def generate_table(self) -> str:
        """Generate the formatted table"""
        num_agents = len(self.agents)
        # Dynamic cell width based on number of agents
        if num_agents <= 2:
            cell_width = 60
        elif num_agents == 3:
            cell_width = 40
        elif num_agents == 4:
            cell_width = 30
        else:  # 5+ agents
            cell_width = 25
        total_width = 10 + (cell_width + 1) * num_agents + 1

        lines = []

        # Top border
        lines.append("+" + "-" * (total_width - 2) + "+")

        # Header row
        header = "|  Round   |"
        for agent in self.agents:
            # Try to create readable agent names
            # Use the full agent name as provided by user configuration
            agent_name = agent
            header += self._format_cell(agent_name, cell_width) + "|"
        lines.append(header)

        # Header separator
        lines.append("|" + "-" * 10 + "+" + ("-" * cell_width + "+") * num_agents)

        # User question row
        question_row = "|   USER   |"
        question_width = cell_width * num_agents + (num_agents - 1)
        question_text = self.user_question.center(question_width)
        question_row += question_text + "|"
        lines.append(question_row)

        # Double separator
        lines.append("|" + "=" * 10 + "+" + ("=" * cell_width + "+") * num_agents)

        # Process each round
        for i, round_data in enumerate(self.rounds):
            # Get content for each agent
            agent_contents = {}
            max_lines = 0

            for agent in self.agents:
                content = self._build_agent_cell_content(
                    round_data.agent_states[agent],
                    round_data.round_type,
                    agent,
                    round_data.round_num,
                )
                agent_contents[agent] = content
                max_lines = max(max_lines, len(content))

            # Build round rows
            for line_idx in range(max_lines):
                row = "|"

                # Round label (only on first line)
                if line_idx == 0:
                    if round_data.round_type == "FINAL":
                        round_label = "  FINAL   "
                    else:
                        round_label = f"   {round_data.round_type}   "
                    row += round_label[-10:].rjust(10) + "|"
                else:
                    row += " " * 10 + "|"

                # Agent cells
                for agent in self.agents:
                    content_lines = agent_contents[agent]
                    if line_idx < len(content_lines):
                        row += self._format_cell(content_lines[line_idx], cell_width)
                    else:
                        row += " " * cell_width
                    row += "|"

                lines.append(row)

            # Round separator
            if i < len(self.rounds) - 1:
                next_round = self.rounds[i + 1]
                if next_round.round_type == "FINAL":
                    # Add winner announcement before FINAL round
                    lines.append(
                        "|" + "-" * 10 + "+" + ("-" * cell_width + "+") * num_agents
                    )

                    # Winner announcement row
                    if self.final_winner:
                        # Use agent mapping for consistent naming
                        agent_number = agent_mapping.get(self.final_winner)
                        if agent_number:
                            winner_name = f"Agent {agent_number}"
                        else:
                            winner_name = self.final_winner

                        winner_text = f"{winner_name} selected as winner"
                        winner_width = (
                            total_width - 1
                        )  # Full table width minus the outer borders
                        winner_row = "|" + winner_text.center(winner_width) + "|"
                        lines.append(winner_row)

                    # Solid line before FINAL
                    lines.append(
                        "|" + "-" * 10 + "+" + ("-" * cell_width + "+") * num_agents
                    )
                else:
                    # Wavy line between regular rounds
                    lines.append(
                        "|" + "~" * 10 + "+" + ("~" * cell_width + "+") * num_agents
                    )

        # Bottom separator
        lines.append("|" + "-" * 10 + "+" + ("-" * cell_width + "+") * num_agents)

        # Bottom border
        lines.append("+" + "-" * (total_width - 2) + "+")

        return "\n".join(lines)

    def _create_rich_legend(self) -> Optional["Panel"]:
        """Create Rich legend panel using shared legend content"""
        try:
            from rich.text import Text
            from rich.panel import Panel
            from rich import box
        except ImportError:
            return None

        legend_data = self._get_legend_content()
        content = Text()

        # Event symbols
        content.append("📋 EVENT SYMBOLS:\n", style="bold bright_blue")
        for symbol, description in legend_data["event_symbols"]:
            padded = f"  {symbol}".ljust(28)
            content.append(f"{padded}- {description}\n", style="dim white")
        content.append("\n")

        # Status symbols
        content.append("📊 STATUS SYMBOLS:\n", style="bold bright_green")
        for symbol, description in legend_data["status_symbols"]:
            padded = f"  {symbol}".ljust(28)
            content.append(f"{padded}- {description}\n", style="dim white")
        content.append("\n")

        # Terms
        content.append("📖 TERMS:\n", style="bold bright_yellow")
        for term, description in legend_data["terms"]:
            if "\n" in description:
                # Handle multi-line descriptions
                lines = description.split("\n")
                content.append(f"  {term.ljust(13)} - {lines[0]}\n", style="dim white")
                for line in lines[1:]:
                    content.append(f"  {line}\n", style="dim white")
            else:
                content.append(
                    f"  {term.ljust(13)} - {description}\n", style="dim white"
                )

        return Panel(
            content,
            title="[bold bright_cyan]📋 COORDINATION GUIDE[/bold bright_cyan]",
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def generate_rich_event_table(self) -> Optional[tuple]:
        """Generate a rich event-driven table with legend

        Returns:
            Tuple of (legend_panel, table) or None if Rich not available
        """
        try:
            from rich.table import Table
            from rich.console import Console
            from rich.text import Text
            from rich import box
        except ImportError:
            return None

        # Create legend first
        legend = self._create_rich_legend()

        # Create the main table
        table = Table(
            title="[bold cyan]Multi-Agent Coordination Events[/bold cyan]",
            box=box.DOUBLE_EDGE,
            expand=True,
            show_lines=True,
        )

        # Add columns
        table.add_column("Event", style="bold yellow", width=8, justify="center")
        for agent in self.agents:
            # Use format "Agent 1 (full_agent_id)"
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num} ({agent})"
            table.add_column(agent_name, style="white", width=45, justify="center")

        # Add user question as header
        question_row = ["[bold cyan]USER[/bold cyan]"]
        question_text = f"[bold white]{self.user_question}[/bold white]"
        for _ in range(len(self.agents)):
            question_row.append(question_text)
        table.add_row(*question_row)

        # Process events chronologically
        agent_states = {
            agent: {
                "status": "idle",
                "context": [],
                "answer": None,
                "vote": None,
                "preview": None,
                "last_streaming_logged": False,
            }
            for agent in self.agents
        }
        event_num = 1

        for event in self.events:
            event_type = event["event_type"]
            agent_id = event.get("agent_id")
            context = event.get("context", {})

            # Handle system events that span both columns
            if event_type == "final_agent_selected":
                winner_name = "Agent1" if "1" in agent_id else "Agent2"
                winner_row = ["[bold green]🏆[/bold green]"]
                winner_text = Text(
                    f"🏆 {winner_name} selected as winner 🏆",
                    style="bold green",
                    justify="center",
                )
                for _ in range(len(self.agents)):
                    winner_row.append(winner_text)
                table.add_row(*winner_row)
                continue
            elif (
                event_type == "restart_triggered"
                and agent_id
                and agent_id in self.agents
            ):
                agent_num = self.agent_mapping.get(agent_id, "?")
                agent_name = f"Agent {agent_num}"
                restart_row = ["[bold yellow]🔁[/bold yellow]"]
                restart_text = Text(
                    f"🔁 {agent_name} RESTART TRIGGERED",
                    style="bold yellow",
                    justify="center",
                )
                for _ in range(len(self.agents)):
                    restart_row.append(restart_text)
                table.add_row(*restart_row)
                continue

            # Skip session-level events
            if not agent_id or agent_id not in self.agents:
                continue

            # Handle agent events
            if event_type == "status_change":
                status = event.get("details", "").replace("Changed to status: ", "")
                old_status = agent_states[agent_id]["status"]
                agent_states[agent_id]["status"] = status

                # Only log first streaming
                if status in ["streaming", "answering"]:
                    if old_status == "voted":
                        pass  # Skip post-vote streaming
                    elif (
                        old_status not in ["streaming", "answering"]
                        or not agent_states[agent_id]["last_streaming_logged"]
                    ):
                        row = self._create_rich_event_row(
                            event_num, agent_id, agent_states, "streaming_start"
                        )
                        if row:
                            table.add_row(*row)
                            event_num += 1
                        agent_states[agent_id]["last_streaming_logged"] = True

            elif event_type == "context_received":
                labels = context.get("available_answer_labels", [])
                agent_states[agent_id]["context"] = labels

            elif event_type == "restart_completed":
                agent_round = context.get("agent_round", context.get("round", 0))
                row = self._create_rich_event_row(
                    event_num, agent_id, agent_states, "restart_completed", agent_round
                )
                if row:
                    table.add_row(*row)
                    event_num += 1
                agent_states[agent_id]["last_streaming_logged"] = False

            elif event_type == "new_answer":
                label = context.get("label")
                if label:
                    agent_states[agent_id]["answer"] = label
                    agent_states[agent_id]["status"] = "answered"
                    agent_states[agent_id]["last_streaming_logged"] = False
                    preview = self.agent_answers.get(agent_id, "")
                    agent_states[agent_id]["preview"] = preview
                    row = self._create_rich_event_row(
                        event_num, agent_id, agent_states, "new_answer", label, preview
                    )
                    if row:
                        table.add_row(*row)
                        event_num += 1

            elif event_type == "vote_cast":
                vote = context.get("voted_for_label")
                reason = context.get("reason", "")
                if vote:
                    agent_states[agent_id]["vote"] = vote
                    agent_states[agent_id]["status"] = "voted"
                    agent_states[agent_id]["last_streaming_logged"] = False
                    row = self._create_rich_event_row(
                        event_num, agent_id, agent_states, "vote", vote, reason
                    )
                    if row:
                        table.add_row(*row)
                        event_num += 1

            elif event_type == "final_answer":
                label = context.get("label")
                if label:
                    agent_states[agent_id]["status"] = "final"
                    preview = agent_states[agent_id].get("preview", "")
                    row = self._create_rich_event_row(
                        event_num,
                        agent_id,
                        agent_states,
                        "final_answer",
                        label,
                        preview,
                    )
                    if row:
                        table.add_row(*row)
                        event_num += 1

        # Add summary section
        self._add_rich_summary(table, agent_states)

        # Return both legend and table
        return (legend, table)

    def _create_rich_event_row(
        self,
        event_num: int,
        active_agent: str,
        agent_states: dict,
        event_type: str,
        *args,
    ) -> list:
        """Create a rich table row for an event"""
        row = [f"[bold yellow]E{event_num}[/bold yellow]"]

        for agent in self.agents:
            if agent == active_agent:
                # Active agent performing the event
                if event_type == "streaming_start":
                    context = agent_states[agent]["context"]
                    context_str = (
                        f"[dim blue]📋 Context: \\[{', '.join(context)}][/dim blue]\n"
                        if context
                        else "[dim blue]📋 Context: \\[][/dim blue]\n"
                    )
                    cell = context_str + "[bold cyan]💭 Started streaming[/bold cyan]"
                elif event_type == "restart_completed":
                    cell = f"[bold green]✅ RESTART COMPLETED (Restart {args[0]})[/bold green]"
                elif event_type == "new_answer":
                    label, preview = args[0], args[1] if len(args) > 1 else ""
                    cell = f"[bold green]✨ NEW ANSWER: {label}[/bold green]"
                    if preview:
                        clean_preview = preview.replace("\n", " ").strip()
                        preview_truncated = (
                            clean_preview[:80] + "..."
                            if len(clean_preview) > 80
                            else clean_preview
                        )
                        cell += f"\n[dim white]👁️  Preview: {preview_truncated}[/dim white]"
                elif event_type == "vote":
                    vote, reason = args[0], args[1] if len(args) > 1 else ""
                    cell = f"[bold cyan]🗳️  VOTE: {vote}[/bold cyan]"
                    if reason:
                        clean_reason = reason.replace("\n", " ").strip()
                        reason_preview = (
                            clean_reason[:50] + "..."
                            if len(clean_reason) > 50
                            else clean_reason
                        )
                        cell += f"\n[italic dim]💭 Reason: {reason_preview}[/italic dim]"
                elif event_type == "final_answer":
                    label, preview = args[0], args[1] if len(args) > 1 else ""
                    cell = f"[bold green]🎯 FINAL ANSWER: {label}[/bold green]"
                    if preview:
                        clean_preview = preview.replace("\n", " ").strip()
                        preview_truncated = (
                            clean_preview[:80] + "..."
                            if len(clean_preview) > 80
                            else clean_preview
                        )
                        cell += f"\n[dim white]👁️  Preview: {preview_truncated}[/dim white]"
                else:
                    cell = ""
                row.append(cell)
            else:
                # Other agents showing status - prioritize active states
                status = agent_states[agent]["status"]
                if status in ["streaming", "answering"]:
                    cell = f"[cyan]🔄 ({status})[/cyan]"
                elif status == "voted":
                    cell = "[green]✅ (voted)[/green]"
                elif status == "answered":
                    if agent_states[agent]["answer"]:
                        cell = f"[green]✅ Answered: {agent_states[agent]['answer']}[/green]"
                    else:
                        cell = "[green]✅ (answered)[/green]"
                elif status == "completed":
                    cell = "[green]✅ (completed)[/green]"
                elif status == "final":
                    cell = "[bold green]🎯 (final answer given)[/bold green]"
                elif status == "idle":
                    cell = "[dim]⏳ (waiting)[/dim]"
                else:
                    cell = f"[dim]({status})[/dim]"
                row.append(cell)

        return row

    def _add_rich_summary(self, table: Any, agent_states: dict) -> None:
        """Add summary statistics to the rich table"""
        # Calculate statistics
        total_answers = sum(1 for agent in self.agents if agent_states[agent]["answer"])
        total_votes = sum(1 for agent in self.agents if agent_states[agent]["vote"])
        total_restarts = len(
            [e for e in self.events if e["event_type"] == "restart_completed"]
        )

        # Summary header
        summary_row = ["[bold magenta]SUMMARY[/bold magenta]"]
        for agent in self.agents:
            agent_num = self.agent_mapping.get(agent, "?")
            agent_name = f"Agent {agent_num}"
            summary_row.append(f"[bold magenta]{agent_name}[/bold magenta]")
        table.add_row(*summary_row)

        # Stats for each agent
        stats_row = ["[bold]Stats[/bold]"]
        for agent in self.agents:
            answer_count = 1 if agent_states[agent]["answer"] else 0
            vote_count = 1 if agent_states[agent]["vote"] else 0
            restart_count = len(
                [
                    e
                    for e in self.events
                    if e["event_type"] == "restart_completed"
                    and e.get("agent_id") == agent
                ]
            )

            status = agent_states[agent]["status"]
            if status == "final":
                status_str = "[bold green]🏆 Winner[/bold green]"
            elif status == "completed":
                status_str = "[green]✅ Completed[/green]"
            else:
                status_str = f"[dim]{status}[/dim]"

            stats = f"{answer_count} answer, {vote_count} vote, {restart_count} restarts\n{status_str}"
            stats_row.append(stats)
        table.add_row(*stats_row)

        # Overall totals
        totals_row = ["[bold]TOTALS[/bold]"]
        totals_text = f"[bold cyan]{total_answers} answers, {total_votes} votes, {total_restarts} restarts[/bold cyan]"
        for _ in range(len(self.agents)):
            totals_row.append(totals_text)
        table.add_row(*totals_row)

    def generate_rich_table(self) -> Optional["Table"]:
        """Generate a Rich table with proper formatting and colors."""
        if not RICH_AVAILABLE:
            return None

        # Create main table with individual agent columns
        table = Table(
            box=box.DOUBLE_EDGE,
            show_header=True,
            header_style="bold bright_white on blue",
            expand=True,
            padding=(0, 1),
            title=f"[bold bright_cyan]Multi-Agent Coordination Flow[/bold bright_cyan]",
            title_style="bold bright_cyan",
        )

        # Add columns with individual agents
        table.add_column("Round", style="bold bright_white", width=14, justify="center")
        for agent in self.agents:
            # Create readable agent names
            # Use the full agent name as provided by user configuration
            agent_name = agent
            # Use fixed width instead of ratio to prevent truncation
            table.add_column(
                agent_name, style="white", justify="center", width=40, overflow="fold"
            )

        # Add user question row - create a nested table to achieve true spanning
        from rich.table import Table as InnerTable

        inner_question_table = InnerTable(
            box=None, show_header=False, expand=True, padding=(0, 0)
        )
        inner_question_table.add_column("Question", justify="center", ratio=1)
        inner_question_table.add_row(
            f"[bold bright_yellow]{self.user_question}[/bold bright_yellow]"
        )

        question_cells = [""]  # Empty round column
        question_cells.append(inner_question_table)
        # Fill remaining columns with empty strings - Rich will merge them visually
        for i in range(len(self.agents) - 1):
            question_cells.append("")
        table.add_row(*question_cells)

        # Add separator row
        separator_cells = ["[dim bright_blue]════════════[/dim bright_blue]"] + [
            "[dim bright_blue]" + "═" * 88 + "[/dim bright_blue]" for _ in self.agents
        ]
        table.add_row(*separator_cells)

        # Process each round
        for i, round_data in enumerate(self.rounds):
            # Get content for each agent
            agent_contents = {}
            max_lines = 0

            for agent in self.agents:
                content = self._build_rich_agent_cell_content(
                    round_data.agent_states[agent],
                    round_data.round_type,
                    agent,
                    round_data.round_num,
                )
                agent_contents[agent] = content
                max_lines = max(max_lines, len(content))

            # Build round rows
            for line_idx in range(max_lines):
                row_cells = []

                # Round label (only on first line)
                if line_idx == 0:
                    if round_data.round_type == "FINAL":
                        round_label = "[bold green]🏁 FINAL 🏁[/bold green]"
                    else:
                        round_label = (
                            f"[bold cyan]🔄 {round_data.round_type} 🔄[/bold cyan]"
                        )
                    row_cells.append(round_label)
                else:
                    row_cells.append("")

                # Agent cells (individual columns)
                for agent in self.agents:
                    content_lines = agent_contents[agent]
                    if line_idx < len(content_lines):
                        row_cells.append(content_lines[line_idx])
                    else:
                        row_cells.append("")

                table.add_row(*row_cells)

            # Round separator
            if i < len(self.rounds) - 1:
                next_round = self.rounds[i + 1]
                if next_round.round_type == "FINAL":
                    # Winner announcement - simulate spanning
                    if self.final_winner:
                        # Use agent mapping for consistent naming
                        agent_number = agent_mapping.get(self.final_winner)
                        if agent_number:
                            winner_name = f"Agent {agent_number}"
                        else:
                            winner_name = self.final_winner

                        winner_announcement = f"🏆 {winner_name} selected as winner 🏆"
                        # Create nested table for winner announcement spanning
                        inner_winner_table = InnerTable(
                            box=None, show_header=False, expand=True, padding=(0, 0)
                        )
                        inner_winner_table.add_column(
                            "Winner", justify="center", ratio=1
                        )
                        inner_winner_table.add_row(
                            f"[bold bright_green]{winner_announcement}[/bold bright_green]"
                        )

                        winner_cells = [""]  # Empty round column
                        winner_cells.append(inner_winner_table)
                        # Fill remaining columns with empty strings
                        for j in range(len(self.agents) - 1):
                            winner_cells.append("")
                        table.add_row(*winner_cells)

                    # Solid line before FINAL
                    separator_cells = ["[dim green]────────────[/dim green]"] + [
                        "[dim green]" + "─" * 88 + "[/dim green]" for _ in self.agents
                    ]
                    table.add_row(*separator_cells)
                else:
                    # Wavy line between regular rounds
                    separator_cells = ["[dim cyan]~~~~~~~~~~~~[/dim cyan]"] + [
                        "[dim cyan]" + "~" * 88 + "[/dim cyan]" for _ in self.agents
                    ]
                    table.add_row(*separator_cells)

        return table

    def _build_rich_agent_cell_content(
        self, agent_state: AgentState, round_type: str, agent_id: str, round_num: int
    ) -> List[str]:
        """Build Rich-formatted content for an agent's cell in a round."""
        lines = []

        # Determine if we should show context (for non-voting scenarios)
        show_context = (
            (agent_state.current_answer and not agent_state.vote)
            or agent_state.has_final_answer
            or agent_state.status in ["streaming", "answering"]
        )

        # Don't show context for completed agents in FINAL round
        if round_type == "FINAL" and agent_state.status == "completed":
            show_context = False

        # Add context with better styling (but not for voting agents)
        if show_context and not agent_state.vote:
            if agent_state.context:
                context_items = ", ".join(agent_state.context)
                context_str = (
                    f"📋 Context: \\[{context_items}]"  # Escape brackets for Rich
                )
            else:
                context_str = "📋 Context: \\[]"  # Escape brackets for Rich
            lines.append(f"[dim blue]{context_str}[/dim blue]")

        # Add content based on what happened in this round with enhanced styling
        if agent_state.vote:
            # Agent voted in this round - always show context when voting
            if agent_state.context:
                context_items = ", ".join(agent_state.context)
                context_str = (
                    f"📋 Context: \\[{context_items}]"  # Escape brackets for Rich
                )
                lines.append(f"[dim blue]{context_str}[/dim blue]")
            vote_str = f"🗳️  VOTE: {agent_state.vote}"
            lines.append(f"[bold cyan]{vote_str}[/bold cyan]")
            if agent_state.vote_reason:
                # Clean up newlines and truncate
                clean_reason = agent_state.vote_reason.replace("\n", " ").strip()
                reason = (
                    clean_reason[:65] + "..."
                    if len(clean_reason) > 68
                    else clean_reason
                )
                reason_str = f"💭 Reason: {reason}"
                lines.append(f"[italic dim]{reason_str}[/italic dim]")

        elif round_type == "FINAL":
            # Final presentation round
            if agent_state.has_final_answer:
                final_str = f"🎯 FINAL ANSWER: {agent_state.current_answer}"
                lines.append(f"[bold green]{final_str}[/bold green]")
                if agent_state.answer_preview:
                    # Clean up newlines in preview
                    clean_preview = agent_state.answer_preview.replace(
                        "\n", " "
                    ).strip()
                    preview_truncated = (
                        clean_preview[:80] + "..."
                        if len(clean_preview) > 80
                        else clean_preview
                    )
                    preview_str = f"👁️  Preview: {preview_truncated}"
                    lines.append(f"[dim white]{preview_str}[/dim white]")
                else:
                    lines.append(
                        f"[dim red]👁️  Preview: [Answer not available][/dim red]"
                    )
            elif agent_state.status == "completed":
                lines.append(f"[dim green]✅ (completed)[/dim green]")
            else:
                lines.append(f"[dim yellow]⏳ (waiting)[/dim yellow]")

        elif agent_state.current_answer and not agent_state.vote:
            # Agent provided an answer in this round
            answer_str = f"✨ NEW ANSWER: {agent_state.current_answer}"
            lines.append(f"[bold green]{answer_str}[/bold green]")
            if agent_state.answer_preview:
                # Clean up newlines in preview
                clean_preview = agent_state.answer_preview.replace("\n", " ").strip()
                preview_truncated = (
                    clean_preview[:80] + "..."
                    if len(clean_preview) > 80
                    else clean_preview
                )
                preview_str = f"👁️  Preview: {preview_truncated}"
                lines.append(f"[dim white]{preview_str}[/dim white]")
            else:
                lines.append(f"[dim red]👁️  Preview: [Answer not available][/dim red]")

        elif agent_state.status in ["streaming", "answering"]:
            lines.append(f"[bold yellow]🔄 (answering)[/bold yellow]")

        elif agent_state.status == "voted":
            lines.append(f"[dim bright_cyan]✅ (voted)[/dim bright_cyan]")

        elif agent_state.status == "answered":
            lines.append(f"[dim bright_green]✅ (answered)[/dim bright_green]")

        else:
            lines.append(f"[dim]⏳ (waiting)[/dim]")

        return lines


def main():
    """Main entry point"""
    # Check for input file
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = "coordination_events.json"

    try:
        # Load events
        with open(filename, "r") as f:
            events = json.load(f)

        # Build and print table
        builder = CoordinationTableBuilder(events)

        # Try to use Rich table first, fallback to plain text
        if RICH_AVAILABLE:
            rich_table = builder.generate_rich_event_table()
            if rich_table:
                console = Console()
                console.print(rich_table)
            else:
                # Fallback to plain event table
                table = builder.generate_event_table()
                print(table)
        else:
            # Use event-driven plain table as default
            table = builder.generate_event_table()
            print(table)

    except FileNotFoundError:
        print(f"Error: Could not find file '{filename}'")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file '{filename}': {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
