#!/usr/bin/env python3
"""
Multi-Agent Coordination Event Table Generator

Parses coordination_events.json and generates a formatted table showing
the progression of agent interactions across rounds.
"""

import json
import sys
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
import textwrap


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
    def __init__(self, events: List[Dict[str, Any]]):
        self.events = events
        self.agents = self._extract_agents()
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
    
    def _extract_user_question(self) -> str:
        """Try to extract the user question from events or use default"""
        # Could be extended to extract from conversation history if available
        return "What's 2+4?"
    
    def _extract_answer_previews(self) -> Dict[str, str]:
        """Extract the actual answer text for each agent"""
        answers = {}
        
        # Try to get from final_agent_selected event
        for event in self.events:
            if event["event_type"] == "final_agent_selected":
                context = event.get("context", {})
                answers_for_context = context.get("answers_for_context", {})
                
                # Map answers to agents
                for key, answer in answers_for_context.items():
                    # Handle both formats: "agent1.1" or "gpt5nano_1"
                    if key in self.agents:
                        answers[key] = answer
                    else:
                        # Try to map label to agent
                        for agent in self.agents:
                            agent_num = agent.split('_')[-1] if '_' in agent else agent
                            if f"agent{agent_num}" in key or key == agent:
                                answers[agent] = answer
                                break
        
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
        regular_rounds = sorted(all_rounds - {self.final_round_num} if self.final_round_num else all_rounds)
        
        # Initialize round states
        rounds = {}
        for r in regular_rounds:
            rounds[r] = {agent: AgentState(round=r) for agent in self.agents}
        
        # Add final round if exists
        if self.final_round_num is not None:
            rounds[self.final_round_num] = {agent: AgentState(round=self.final_round_num) for agent in self.agents}
        
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
                    round_num = self.final_round_num if self.final_round_num else context.get("round", 0)
                
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
                                agent_state.answer_preview = self.agent_answers[agent_id]
                            
                    elif event_type == "vote_cast":
                        agent_state.vote = context.get("voted_for_label")
                        agent_state.vote_reason = context.get("reason")
                        agent_state.has_voted = True
                        
                    elif event_type == "final_answer":
                        agent_state.has_final_answer = True
                        agent_state.current_answer = context.get("label")
                        agent_state.is_final = True
                        if agent_id in self.agent_answers:
                            agent_state.answer_preview = self.agent_answers[agent_id]
                            
                    elif event_type == "final_agent_selected":
                        agent_state.is_selected_winner = True
                        
                    elif event_type == "status_change":
                        status = event.get("details", "").replace("Changed to status: ", "")
                        agent_state.status = status
        
        # Mark non-winner as terminated in FINAL round
        if self.final_winner and self.final_round_num in rounds:
            for agent in self.agents:
                if agent != self.final_winner:
                    rounds[self.final_round_num][agent].status = "completed"
        
        # Build final round list
        round_list = []
        
        # Add regular rounds
        for r in regular_rounds:
            round_type = f"R{r}"
            round_list.append(RoundData(r, round_type, rounds.get(r, {agent: AgentState() for agent in self.agents})))
        
        # Add FINAL round if exists
        if self.final_round_num is not None and self.final_round_num in rounds:
            round_list.append(RoundData(self.final_round_num, "FINAL", rounds[self.final_round_num]))
            
        return round_list
    
    def _format_cell(self, content: str, width: int) -> str:
        """Format content to fit within cell width, centered"""
        if not content:
            return " " * width
        
        if len(content) <= width:
            return content.center(width)
        else:
            # Truncate if too long
            truncated = content[:width-3] + "..."
            return truncated.center(width)
    
    def _build_agent_cell_content(self, agent_state: AgentState, round_type: str, 
                                  agent_id: str, round_num: int) -> List[str]:
        """Build the content for an agent's cell in a round"""
        lines = []
        
        # Determine if we should show context (but not for voting agents)
        # Show context only if agent is doing something meaningful with it (but not voting)
        show_context = (
            (agent_state.current_answer and not agent_state.vote) or  # Agent answered (but didn't vote)
            agent_state.has_final_answer or  # Agent has final answer
            agent_state.status in ["streaming", "answering"]  # Agent is actively working
        )
        
        # Don't show context for terminated agents in FINAL round
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
            # Agent voted in this round - show Options first, then vote
            if agent_state.context:
                lines.append(f"Options: [{', '.join(agent_state.context)}]")
            lines.append(f"VOTE: {agent_state.vote}")
            if agent_state.vote_reason:
                reason = agent_state.vote_reason[:47] + "..." if len(agent_state.vote_reason) > 50 else agent_state.vote_reason
                lines.append(f"Reason: {reason}")
        
        elif round_type == "FINAL":
            # Final presentation round
            if agent_state.has_final_answer:
                lines.append(f"FINAL ANSWER: {agent_state.current_answer}")
                if agent_state.answer_preview:
                    lines.append(f"Preview: {agent_state.answer_preview}")
                else:
                    lines.append("Preview: [Answer not available]")
            elif agent_state.status == "completed":
                lines.append("(terminated)")
            else:
                lines.append("(waiting)")
        
        elif agent_state.current_answer and not agent_state.vote:
            # Agent provided an answer in this round
            lines.append(f"NEW ANSWER: {agent_state.current_answer}")
            if agent_state.answer_preview:
                lines.append(f"Preview: {agent_state.answer_preview}")
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
    
    def generate_table(self) -> str:
        """Generate the formatted table"""
        cell_width = 60
        num_agents = len(self.agents)
        total_width = 10 + (cell_width + 1) * num_agents + 1
        
        lines = []
        
        # Top border
        lines.append("+" + "-" * (total_width - 2) + "+")
        
        # Header row
        header = "|  Round   |"
        for agent in self.agents:
            # Try to create readable agent names
            if '_' in agent:
                parts = agent.split('_')
                agent_name = f"Agent{parts[-1]}"
            else:
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
                    round_data.round_num
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
                    lines.append("|" + "-" * 10 + "+" + ("-" * cell_width + "+") * num_agents)
                    
                    # Winner announcement row
                    if self.final_winner:
                        # Try to create readable agent name
                        if '_' in self.final_winner:
                            parts = self.final_winner.split('_')
                            winner_name = f"Agent{parts[-1]}"
                        else:
                            winner_name = self.final_winner
                        
                        winner_text = f"{winner_name} selected as winner"
                        winner_row = "| WINNER   |"
                        winner_width = cell_width * num_agents + (num_agents - 1)
                        winner_row += winner_text.center(winner_width) + "|"
                        lines.append(winner_row)
                    
                    # Solid line before FINAL
                    lines.append("|" + "-" * 10 + "+" + ("-" * cell_width + "+") * num_agents)
                else:
                    # Wavy line between regular rounds
                    lines.append("|" + "~" * 10 + "+" + ("~" * cell_width + "+") * num_agents)
        
        # Bottom separator
        lines.append("|" + "-" * 10 + "+" + ("-" * cell_width + "+") * num_agents)
        
        # Bottom border  
        lines.append("+" + "-" * (total_width - 2) + "+")
        
        return "\n".join(lines)


def main():
    """Main entry point"""
    # Check for input file
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = "coordination_events.json"
    
    try:
        # Load events
        with open(filename, 'r') as f:
            events = json.load(f)
        
        # Build and print table
        builder = CoordinationTableBuilder(events)
        table = builder.generate_table()
        
        # Add line numbers if desired (optional)
        lines = table.split('\n')
        max_line_num = len(lines)
        numbered_lines = []
        for i, line in enumerate(lines, 1):
            # Right-align line numbers (counting down)
            line_num = str(max_line_num - i + 1).rjust(3)
            numbered_lines.append(f"{line_num} {line}")
        
        print("\n".join(numbered_lines))
        
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
