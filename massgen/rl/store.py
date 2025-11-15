"""
Lightning Store - Local Filesystem Implementation

This module provides local filesystem-based storage for RL traces,
following the design from massgen_rl_integration_design.md
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import asyncio

from .trace import Trace
from .config import StoreConfig


class LightningStore:
    """
    Local filesystem-based store for RL traces.

    Stores traces as JSON files organized by date and agent.
    """

    def __init__(self, config: StoreConfig):
        """
        Initialize store with configuration.

        Args:
            config: Store configuration
        """
        self.config = config
        self.base_path = Path(config.path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        self.traces_path = self.base_path / "traces"
        self.traces_path.mkdir(exist_ok=True)

        self.metadata_path = self.base_path / "metadata"
        self.metadata_path.mkdir(exist_ok=True)

    async def save_trace(self, trace: Trace) -> bool:
        """
        Save a trace to storage.

        Args:
            trace: Trace object to save

        Returns:
            True if save was successful
        """
        try:
            # Organize by date and agent
            date_str = datetime.fromtimestamp(trace.start_time).strftime("%Y%m%d")
            agent_dir = self.traces_path / date_str / trace.agent_id
            agent_dir.mkdir(parents=True, exist_ok=True)

            # Save trace as JSON
            trace_file = agent_dir / f"{trace.trace_id}.json"
            trace_data = trace.to_dict()

            # Write asynchronously
            await asyncio.to_thread(self._write_json, trace_file, trace_data)

            # Update metadata
            await self._update_metadata(trace)

            return True
        except Exception as e:
            print(f"Error saving trace {trace.trace_id}: {e}")
            return False

    def _write_json(self, file_path: Path, data: dict):
        """Write JSON data to file synchronously"""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    async def load_trace(self, trace_id: str) -> Optional[Trace]:
        """
        Load a trace by ID.

        Args:
            trace_id: Trace ID to load

        Returns:
            Trace object if found, None otherwise
        """
        try:
            # Search for trace in metadata
            trace_file = await self._find_trace_file(trace_id)
            if not trace_file:
                return None

            # Load trace data
            trace_data = await asyncio.to_thread(self._read_json, trace_file)
            return Trace.from_dict(trace_data)
        except Exception as e:
            print(f"Error loading trace {trace_id}: {e}")
            return None

    def _read_json(self, file_path: Path) -> dict:
        """Read JSON data from file synchronously"""
        with open(file_path, 'r') as f:
            return json.load(f)

    async def _find_trace_file(self, trace_id: str) -> Optional[Path]:
        """Find trace file by searching the traces directory"""
        for trace_file in self.traces_path.rglob(f"{trace_id}.json"):
            return trace_file
        return None

    async def get_traces_by_agent(self, agent_id: str, limit: Optional[int] = None) -> List[Trace]:
        """
        Get all traces for a specific agent.

        Args:
            agent_id: Agent ID
            limit: Maximum number of traces to return

        Returns:
            List of traces
        """
        traces = []
        count = 0

        try:
            # Search all date directories
            for date_dir in sorted(self.traces_path.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue

                agent_dir = date_dir / agent_id
                if not agent_dir.exists():
                    continue

                # Load traces from this directory
                for trace_file in sorted(agent_dir.glob("*.json"), reverse=True):
                    if limit and count >= limit:
                        return traces

                    trace_data = await asyncio.to_thread(self._read_json, trace_file)
                    traces.append(Trace.from_dict(trace_data))
                    count += 1

        except Exception as e:
            print(f"Error getting traces for agent {agent_id}: {e}")

        return traces

    async def get_all_traces(self, limit: Optional[int] = None) -> List[Trace]:
        """
        Get all traces from storage.

        Args:
            limit: Maximum number of traces to return

        Returns:
            List of traces
        """
        traces = []
        count = 0

        try:
            # Search all trace files
            for trace_file in sorted(self.traces_path.rglob("*.json"), reverse=True):
                if limit and count >= limit:
                    break

                trace_data = await asyncio.to_thread(self._read_json, trace_file)
                traces.append(Trace.from_dict(trace_data))
                count += 1

        except Exception as e:
            print(f"Error getting all traces: {e}")

        return traces

    async def _update_metadata(self, trace: Trace):
        """Update metadata index for faster lookups"""
        try:
            metadata_file = self.metadata_path / "trace_index.json"

            # Load existing metadata
            if metadata_file.exists():
                metadata = await asyncio.to_thread(self._read_json, metadata_file)
            else:
                metadata = {"traces": {}, "agents": {}}

            # Update trace index
            metadata["traces"][trace.trace_id] = {
                "agent_id": trace.agent_id,
                "task": trace.task[:100],  # Truncate long tasks
                "start_time": trace.start_time,
                "status": trace.status,
                "total_reward": trace.total_reward
            }

            # Update agent index
            if trace.agent_id not in metadata["agents"]:
                metadata["agents"][trace.agent_id] = []
            metadata["agents"][trace.agent_id].append(trace.trace_id)

            # Save metadata
            await asyncio.to_thread(self._write_json, metadata_file, metadata)

        except Exception as e:
            print(f"Error updating metadata: {e}")

    async def get_statistics(self) -> Dict:
        """
        Get storage statistics.

        Returns:
            Dictionary with statistics
        """
        try:
            metadata_file = self.metadata_path / "trace_index.json"
            if not metadata_file.exists():
                return {
                    "total_traces": 0,
                    "total_agents": 0,
                    "total_reward": 0.0
                }

            metadata = await asyncio.to_thread(self._read_json, metadata_file)

            total_reward = sum(
                trace_info.get("total_reward", 0.0) or 0.0
                for trace_info in metadata["traces"].values()
            )

            return {
                "total_traces": len(metadata["traces"]),
                "total_agents": len(metadata["agents"]),
                "total_reward": total_reward,
                "agents": {
                    agent_id: len(trace_ids)
                    for agent_id, trace_ids in metadata["agents"].items()
                }
            }
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {}

    def clear_all(self):
        """Clear all stored data (use with caution!)"""
        import shutil
        if self.base_path.exists():
            shutil.rmtree(self.base_path)
            self.base_path.mkdir(parents=True, exist_ok=True)
            self.traces_path.mkdir(exist_ok=True)
            self.metadata_path.mkdir(exist_ok=True)
