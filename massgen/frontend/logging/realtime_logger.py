"""
Real-time Logger for MassGen Coordination

Provides comprehensive logging of coordination sessions with live updates.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional


class RealtimeLogger:
    """Real-time logger for MassGen coordination sessions."""

    def __init__(self, filename: Optional[str] = None, update_frequency: int = 5):
        """Initialize the real-time logger.

        Args:
            filename: Custom filename for log (default: auto-generated)
            update_frequency: Update log file every N chunks (default: 5)
        """
        self.update_frequency = update_frequency
        self.chunk_count = 0

        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.filename = f"mass_coordination_{timestamp}.json"
        else:
            self.filename = filename

        # Initialize log data structure
        self.log_data = {
            "metadata": {
                "start_time": datetime.now().isoformat(),
                "status": "in_progress",
                "logger_version": "1.0",
            },
            "session": {"question": "", "agent_ids": [], "final_answer": ""},
            "agent_outputs": {},
            "orchestrator_events": [],
            "aggregated_responses": {},
            "workflow_analysis": {"new_answers": 0, "votes": 0, "total_chunks": 0},
        }

        # Track aggregated content by source
        self._content_buffers = {}

    def initialize_session(self, question: str, agent_ids: List[str]):
        """Initialize a new coordination session.

        Args:
            question: The coordination question
            agent_ids: List of participating agent IDs
        """
        self.log_data["session"]["question"] = question
        self.log_data["session"]["agent_ids"] = agent_ids
        self.log_data["agent_outputs"] = {agent_id: [] for agent_id in agent_ids}

        # Write initial log file
        self._update_log_file()

        return self.filename

    def log_chunk(
        self, source: Optional[str], content: str, chunk_type: str = "content"
    ):
        """Log a streaming chunk by aggregating content by source.

        Args:
            source: Source of the chunk (agent ID or orchestrator)
            content: Content of the chunk
            chunk_type: Type of chunk ("content", "tool_calls", "done")
        """
        self.chunk_count += 1
        self.log_data["workflow_analysis"]["total_chunks"] = self.chunk_count

        # Initialize buffer for this source if not exists
        source_key = source or "orchestrator"
        if source_key not in self._content_buffers:
            self._content_buffers[source_key] = {
                "thinking": "",
                "tool": "",
                "presentation": "",
                "other": "",
                "first_timestamp": datetime.now().isoformat(),
                "last_timestamp": datetime.now().isoformat(),
            }

        # Aggregate content by type
        content_type = (
            chunk_type
            if chunk_type in ["thinking", "tool", "presentation"]
            else "other"
        )
        self._content_buffers[source_key][content_type] += content
        self._content_buffers[source_key]["last_timestamp"] = datetime.now().isoformat()

        # Track tool usage
        if "🔧 Using new_answer tool:" in content:
            self.log_data["workflow_analysis"]["new_answers"] += 1
        elif "🔧 Using vote tool:" in content:
            self.log_data["workflow_analysis"]["votes"] += 1

        # Update aggregated responses in log data
        self.log_data["aggregated_responses"] = {}
        for src, buffer in self._content_buffers.items():
            self.log_data["aggregated_responses"][src] = {
                "thinking": buffer["thinking"].strip(),
                "tool_calls": buffer["tool"].strip(),
                "presentation": buffer["presentation"].strip(),
                "other_content": buffer["other"].strip(),
                "first_timestamp": buffer["first_timestamp"],
                "last_timestamp": buffer["last_timestamp"],
            }

        # Update log file periodically
        if self.chunk_count % self.update_frequency == 0:
            self._update_log_file()

    def log_agent_content(
        self, agent_id: str, content: str, content_type: str = "thinking"
    ):
        """Log agent-specific content.

        Args:
            agent_id: The agent ID
            content: The content to log
            content_type: Type of content ("thinking", "tool", "status")
        """
        if agent_id in self.log_data["agent_outputs"]:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": content_type,
                "content": content,
            }
            self.log_data["agent_outputs"][agent_id].append(entry)

    def log_orchestrator_event(self, event: str):
        """Log an orchestrator coordination event.

        Args:
            event: The coordination event description
        """
        event_entry = {"timestamp": datetime.now().isoformat(), "event": event}
        self.log_data["orchestrator_events"].append(event_entry)

    def finalize_session(self, final_answer: str = "", success: bool = True):
        """Finalize the coordination session.

        Args:
            final_answer: The final coordinated answer
            success: Whether coordination was successful
        """
        self.log_data["metadata"]["end_time"] = datetime.now().isoformat()
        self.log_data["metadata"]["status"] = "completed" if success else "failed"
        self.log_data["session"]["final_answer"] = final_answer

        # Calculate session duration
        start_time = datetime.fromisoformat(self.log_data["metadata"]["start_time"])
        end_time = datetime.fromisoformat(self.log_data["metadata"]["end_time"])
        duration = (end_time - start_time).total_seconds()
        self.log_data["metadata"]["duration_seconds"] = duration

        # Final log file update
        self._update_log_file()

        return {
            "filename": self.filename,
            "duration": duration,
            "total_chunks": self.chunk_count,
            "orchestrator_events": len(self.log_data["orchestrator_events"]),
            "success": success,
        }

    def get_log_filename(self) -> str:
        """Get the current log filename."""
        return self.filename

    def get_monitoring_commands(self) -> Dict[str, str]:
        """Get commands for monitoring the log file."""
        return {
            "tail": f"tail -f {self.filename}",
            "watch": f"watch -n 1 'tail -20 {self.filename}'",
            "code": f"code {self.filename}",
            "less": f"less +F {self.filename}",
        }

    def _update_log_file(self):
        """Update the log file with current data."""
        try:
            with open(self.filename, "w") as f:
                json.dump(self.log_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # Silently fail to avoid disrupting coordination
            pass
